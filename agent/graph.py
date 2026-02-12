from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import generate_question, evaluate_answer
from agent.logger import get_logger

logger = get_logger(__name__)

def route_start(state: AgentState):
    """
    Determine if we should evaluate an answer or just generate a question.
    """
    # If we have a current question AND a user answer in history that hasn't been evaluated...?
    # A simpler check: Check if 'evaluations' count matches 'question_count'.
    # If question_count > len(evaluations), it means we asked a question but haven't evaluated it yet?
    # No, question_count increments when we ask.
    # So if we have asked 1 question, and have 0 evaluations, but we have a user answer, we should evaluate.
    
    # Actually, simpler: check if the last message was from the user.
    history = state.get("history", [])
    if history and history[-1]["role"] == "user":
        logger.debug("Routing to evaluate_answer")
        return "evaluate_answer"
    logger.debug("Routing to generate_question")
    return "generate_question"

import config

def route_next_step(state: AgentState):
    """
    Determine if we should continue generating questions or end the interview.
    """
    if state.get("question_count", 0) >= config.MAX_QUESTIONS_DEFAULT:
        logger.info("Max questions reached. Ending interview.")
        return END
    logger.debug("Continuing interview. Generating next question.")
    return "generate_question"

def create_graph():
    logger.info("Creating StateGraph")
    builder = StateGraph(AgentState)
    
    builder.add_node("generate_question", generate_question)
    builder.add_node("evaluate_answer", evaluate_answer)
    
    # Start -> Router
    builder.set_conditional_entry_point(
        route_start,
        {
            "evaluate_answer": "evaluate_answer",
            "generate_question": "generate_question"
        }
    )
    
    # Evaluate -> Router (Generate or End)
    builder.add_conditional_edges(
        "evaluate_answer",
        route_next_step,
        {
            "generate_question": "generate_question",
            END: END
        }
    )
    
    # Generate -> End (Wait for user input loop)
    # Note: In our current app structure, 'generate_question' returns to app, app waits for input.
    # So 'generate_question' effectively ends the *graph run* but not the *session*.
    builder.add_edge("generate_question", END)
    
    return builder.compile()
