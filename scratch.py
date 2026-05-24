import asyncio
import sys
import os
from backend.orchestration.graph import run_workflow

async def main():
    query = "I have a 68-year-old male patient presenting to the emergency room with worsening shortness of breath, bilateral lower extremity edema, and severe fatigue for the past 3 days."
    print("Running workflow...")
    state = await run_workflow(query=query)
    print("Done! Final path:", state.get("workflow_path"))

if __name__ == "__main__":
    asyncio.run(main())
