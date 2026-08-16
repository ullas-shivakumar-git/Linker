from fastapi import FastAPI

from app.api.routes import credentials, node_types, workflows, workspaces

app = FastAPI()

app.include_router(workspaces.router)
app.include_router(credentials.router)
app.include_router(workflows.router)
app.include_router(node_types.router)


@app.get("/health")
async def health_check():
    return {"state": "Healthy"}