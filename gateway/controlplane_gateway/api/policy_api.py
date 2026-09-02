import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1", tags=["policy"])

# We assume gateway is run from the `gateway` or root folder, and policies are in ../policies
# In the original structure, it's at `<root>/policies/`
POLICY_DIR = Path(__file__).parent.parent.parent.parent / "policies"


class PolicyContent(BaseModel):
    content: str


@router.get("/policies")
async def list_policies():
    """List all YAML files in the policies directory."""
    policies = []
    if POLICY_DIR.exists() and POLICY_DIR.is_dir():
        for root, _, files in os.walk(POLICY_DIR):
            for file in files:
                if file.endswith((".yaml", ".yml")):
                    rel_path = Path(root).joinpath(file).relative_to(POLICY_DIR)
                    policies.append(str(rel_path))
    return {"policies": policies}


@router.get("/policies/{path:path}")
async def get_policy(path: str):
    """Get the raw content of a policy file."""
    if not path.endswith(".yaml") and not path.endswith(".yml"):
        path += ".yaml"
        
    full_path = POLICY_DIR / path
    try:
        # Prevent directory traversal
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(POLICY_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Invalid path")
            
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="Policy not found")
            
        with open(full_path, "r") as f:
            return {"content": f.read()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/policies/{path:path}")
async def update_policy(path: str, body: PolicyContent):
    """Update a policy file's content."""
    if not path.endswith(".yaml") and not path.endswith(".yml"):
        path += ".yaml"
        
    full_path = POLICY_DIR / path
    try:
        # Prevent directory traversal
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(POLICY_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Invalid path")
            
        if not full_path.exists() or not full_path.is_file():
            # Allow creation if the directory exists? We'll only allow modifying existing for safety,
            # or creating if it's within a known subfolder. Let's allow creating.
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
        with open(full_path, "w") as f:
            f.write(body.content)
            
        # Note: If the PolicyEngine is active, it needs to reload. In this prototype,
        # it might just load on start. The user might have to restart the gateway, 
        # or we could trigger a reload. We'll leave it as disk update for now.
        return {"status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
