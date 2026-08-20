import os
import subprocess
from typing import List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 1. Load environment and initialize client
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 2. Define Pydantic Schemas
class BashStep(BaseModel):
    explanation: str = Field(description="Short rationale for this specific command")
    command: str = Field(description="The exact executable bash command")
    is_safe: bool = Field(description="Set to False if command deletes, overwrites, or alters system files")

class BashExecutionPlan(BaseModel):
    summary: str = Field(description="Overview of what this plan accomplishes")
    steps: List[BashStep]

# 3. Main Agent Execution Function
def run_agent_prompt(prompt: str):
    print(f"\n--- Processing User Request: '{prompt}' ---")
    
    # Generate structured content with Pydantic enforcement
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BashExecutionPlan,
            temperature=0.1,  # Low temperature for deterministic output
        ),
    )

    # 4. Access the parsed Pydantic object directly
    plan: BashExecutionPlan = response.parsed
    print(f"\n[Plan Summary]: {plan.summary}\n")
    print(f"\nNumber of steps prepared: {len(plan.steps)}")

    # 5. Execute steps sequentially with safety confirmation
    for i, step in enumerate(plan.steps, 1):
        safety_tag = "SAFE" if step.is_safe else "WARNING: POTENTIALLY DESTRUCTIVE"
        print(f"Step {i} [{safety_tag}]:")
        print(f"  Rationale: {step.explanation}")
        print(f"  Command:   {step.command}")
        
        confirm = input("Execute step? (y/N): ").strip().lower()
        if confirm != 'y':
            print(" Skipping step by user request.\n")
            continue

        # Run command via subprocess
        try:
            result = subprocess.run(
                step.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print(f" Output:\n{result.stdout.strip()}\n")
            else:
                print(f" Error (code {result.returncode}):\n{result.stderr.strip()}\n")
                
        except subprocess.TimeoutExpired:
            print(" Execution timed out after 30 seconds.\n")

if __name__ == "__main__":
    test_user_prompt = input("Introduce the desired prompt ")
    run_agent_prompt(test_user_prompt)