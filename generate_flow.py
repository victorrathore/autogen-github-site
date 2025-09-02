import os
import asyncio
import re
from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
import git
import yaml

# --- Load .env ---
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in .env file!")

# --- Config ---
REPO_PATH = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/victorrathore/autogen-github-site.git"  # your repo
INDEX_FILE = os.path.join(REPO_PATH, "index.html")

# --- Ensure index.html exists ---
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "w") as f:
        f.write("<!DOCTYPE html><html><body><h1>Hello from Autogen Agent!</h1></body></html>")

# --- Clone or init repo ---
if not os.path.exists(os.path.join(REPO_PATH, ".git")):
    repo = git.Repo.init(REPO_PATH)
else:
    repo = git.Repo(REPO_PATH)

# --- Ensure main branch exists ---
if repo.head.is_detached or repo.active_branch.name != "main":
    if "main" in repo.heads:
        repo.head.reference = repo.heads["main"]
    else:
        repo.git.checkout("-b", "main")

# --- Autogen Agent prompt ---
prompt = """
Generate a GitHub Actions workflow YAML file for a static HTML site.
The workflow should:
1. Trigger on push to main branch.
2. Checkout the code.
3. Deploy the site automatically to GitHub Pages.
4. Do NOT include any Node.js or npm steps.
Return only valid YAML content.
"""

# --- Initialize Agent ---
model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=api_key)
agent = AssistantAgent(
    name="assistant",
    model_client=model_client
)

async def main():
    # --- Generate workflow asynchronously ---
    workflow_task = await agent.run(task=prompt)
    workflow_text = workflow_task.messages[-1].content  # final response

    # --- Clean code fences ---
    workflow_text = re.sub(r"```[a-zA-Z]*", "", workflow_text)
    workflow_text = workflow_text.replace("```", "").strip()

    # --- Keep only valid YAML lines ---
    clean_lines = []
    for line in workflow_text.splitlines():
        stripped = line.strip()
        if stripped == "" or re.match(r"^(\w+):", stripped) or re.match(r"^- ", stripped) or line.startswith(" "):
            clean_lines.append(line)
    workflow_text = "\n".join(line.rstrip() for line in clean_lines)

    # --- Validate YAML ---
    try:
        yaml.safe_load(workflow_text)
    except yaml.YAMLError as e:
        print("YAML syntax error:", e)
        raise

    # --- Save workflow ---
    workflow_dir = os.path.join(REPO_PATH, ".github", "workflows")
    os.makedirs(workflow_dir, exist_ok=True)
    workflow_file = os.path.join(workflow_dir, "deploy.yml")
    with open(workflow_file, "w") as f:
        f.write(workflow_text)
    print("Workflow generated at:", workflow_file)

    # --- Git commit & push only if changes ---
    if repo.is_dirty(untracked_files=True):
        repo.git.add(all=True)
        repo.index.commit("Autogen update: index.html + workflow")
        if "origin" not in [r.name for r in repo.remotes]:
            origin = repo.create_remote("origin", REPO_URL)
        else:
            origin = repo.remote(name="origin")
        origin.push(refspec="main:main")
        print("Changes committed and pushed to GitHub")
    else:
        print("No changes to commit. Agent finished.")

# --- Run async main ---
asyncio.run(main())
