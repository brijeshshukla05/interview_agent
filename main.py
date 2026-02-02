import sys
import os
from langchain_core.messages import HumanMessage, AIMessage

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.graph import create_graph
from agent.state import AgentState

def main():
    print("Welcome to the AI Interview Agent!")
    topics_input = input("Please enter the topics you would like to be interviewed on (comma separated): ")
    topics = [t.strip() for t in topics_input.split(",") if t.strip()]
    
    if not topics:
        print("No topics selected. Exiting.")
        return

    # Initialize State
    state: AgentState = {
        "topics": topics,
        "history": [],
        "current_question": None,
        "evaluations": [],
        "complexity_level": 1,
        "question_count": 0,
        "exit_session": False,
        "question_bank": [],
        "bank_index": 0
    }
    
    graph = create_graph()
    
    print(f"\nStarting interview on: {', '.join(topics)}")
    print("Type 'exit' at any time to finish the interview.\n")
    
    while True:
        # invoke graph
        # The graph will self-route:
        # 1. First run: history empty -> generate_question -> END
        # 2. Subsequent: history has user answer -> evaluate -> generate -> END
        
        result = graph.invoke(state)
        
        # Update our local state with result
        # Note: result contains the final state after the graph run
        state = result 
        
        # Print the question
        if state["current_question"]:
            print(f"\nAI Interviewer (Level {state['complexity_level']}): {state['current_question']}")
            
            # Update history with AI question (we didn't do this inside the node to keep it pure-ish config-wise, 
            # but usually we want to track it)
            # Let's ensure we append the AI question to history so the NEXT prompt sees it.
            # The 'generate_question' node didn't append to history in my implementation, 
            # so I should handle it here or update the node. 
            # Updating the node is cleaner, but let's do it here for explicit control.
            
            # Actually, I should check if the Last history item is already this question? 
            # No, 'generate_question' just returned the string.
            
            state["history"].append({"role": "assistant", "content": state["current_question"]})
        
        # Get User Input
        user_input = input("\nYou: ")
        
        if user_input.lower().strip() == "exit":
            break
            
        # Add user answer to history
        state["history"].append({"role": "user", "content": user_input})
        
        # Loop continues, next invoke will see user answer and route to evaluate -> generate
        
    # End Session Report
    print("\n\n=== Interview Completed ===")
    print("Evaluation Report:")
    
    if not state["evaluations"]:
        print("No questions answered.")
    else:
        total_score = 0
        for i, ev in enumerate(state["evaluations"], 1):
            print(f"\nQ{i}: {ev['question']}")
            print(f"A: {ev['user_answer']}")
            print(f"Score: {ev['score']}/10")
            print(f"Feedback: {ev['feedback']}")
            total_score += ev['score']
            
        avg_score = total_score / len(state["evaluations"])
        print(f"\nAverage Score: {avg_score:.1f}/10")
        print("Thank you for using the Interview Agent!")

if __name__ == "__main__":
    main()
