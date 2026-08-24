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

# 3. Main Agent Execution Function with Dynamic Self-Healing
def run_agent_prompt(prompt: str):
    print(f"\n--- Processing User Request: '{prompt}' ---")
    
    # Create a persistent chat session with schema enforcement
    chat = client.chats.create(
        model="gemini-3.6-flash",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BashExecutionPlan,
            temperature=0.1,
            system_instruction="You are an automated bash script generator. Always issue commands compatible with the current working environment."
        )
    )

    # Initial request to populate chat context
    response = chat.send_message(prompt)

    # Outer control loop: Handles plan replacement on failures
    while True:
        plan: BashExecutionPlan = response.parsed
        print(f"\n[Plan Summary]: {plan.summary}")
        print(f"Number of steps prepared: {len(plan.steps)}\n")

        plan_failed = False

        if not plan.steps:
            print("\n[Agent]: No steps generated or remaining. Task complete or unachievable.")
            break

        # Inner execution loop: Iterates step-by-step
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
                    
                    retry = input("Step failed. Feed error back to Gemini to repair remaining plan? (y/N): ").strip().lower()
                    if retry == 'y':
                        error_prompt = (
                            f"Command '{step.command}' failed with exit code {result.returncode}.\n"
                            f"Stderr output:\n{result.stderr.strip()}\n"
                            "Please provide a revised execution plan to complete the original task, replacing the failed step."
                        )
                        print("\n--- Requesting Plan Repair from Gemini ---")
                        # Get a fresh plan via chat history, then break to restart the outer loop
                        response = chat.send_message(error_prompt)
                        plan_failed = True
                        break
                    else:
                        print(" Halting plan execution.\n")
                        return

            except subprocess.TimeoutExpired:
                print(" Execution timed out after 30 seconds.\n")

        # If all steps in the current plan finished without triggering a failure break, exit function
        if not plan_failed:
            print("--- Plan execution complete ---")
            break

if __name__ == "__main__":
    test_user_prompt = input("Introduce the desired prompt: ")
    run_agent_prompt(test_user_prompt)