from agent.state import AgentState, Evaluation
from agent.utils import get_llm, extract_json
from prompts.templates import TOPIC_SOLICITATION, QUESTION_GENERATION, EVALUATION
from langchain_core.messages import HumanMessage, SystemMessage
import config
import random
from agent.logger import get_logger

logger = get_logger(__name__)

def get_topics(state: AgentState):
    """
    This node effectively just acts as a pass-through or initialization in this design,
    as we might handle initial topic gathering via CLI input before invoking the graph,
    OR we can have a node that asks for it.
    
    For this 'chat based' flow, let's assume the user input for topics comes in *before* 
    we enter the main loop, or at the very start.
    
    If topics are empty, we might prompt the user. But in a LangGraph CLI, we typically
    inject state.
    """
    pass

def generate_question(state: AgentState):
    """
    Generates a question based on current topics and complexity.
    """
    logger.info("Generating question")
    topics = ", ".join(state["topics"])
    complexity = state.get("complexity_level", 1)
    history = state.get("history", [])
    question_bank = state.get("question_bank", []) or []
    bank_index = state.get("bank_index", 0)
    
    # Format history for prompt
    history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history]) # Use full context for variety check
    
    # Always ask conceptual/theoretical questions (no coding/practical)
    question_type = "conceptual/theoretical"

    use_bank = False
    if question_bank:
        if config.BANK_ASK_EVERY and (state.get("question_count", 0) % config.BANK_ASK_EVERY == 0):
            use_bank = True
    
    if use_bank:
        pick_idx = random.randrange(len(question_bank))
        question_text = question_bank.pop(pick_idx).strip()
        logger.info(f"Picked question from bank: {question_text}")
        bank_index += 1
    else:
        logger.debug("Generating question via LLM")
        prompt = QUESTION_GENERATION.format(
            topics=topics,
            complexity_level=complexity,
            history=history_str,
            question_type=question_type,
            years_of_experience=state.get("years_of_experience", 0)
        )
        
        llm = get_llm(temperature=config.TEMPERATURE_ASK, max_tokens=config.MAX_TOKENS_QUESTION)
        response = llm.invoke([HumanMessage(content=prompt)])
        question_text = response.content.strip()
        logger.info(f"Generated Question: {question_text}")
    
    # Update state
    return {
        "current_question": question_text,
        "bank_index": bank_index,
        "question_bank": question_bank,
        # We don't append to history here yet, we append when we send it to user? 
        # Or we can append now. Let's append now for the record.
        # Actually, standard pattern: update state, then external loop prints it.
    }

def evaluate_answer(state: AgentState):
    """
    Evaluates the user's answer to the current question.
    """
    logger.info("Evaluating answer")
    question = state["current_question"]
    # User answer should have been put into state by the human_input handling part of the loop
    # We'll assume the last message in history is the user's answer, OR we have a field.
    # Let's look at State. We don't have a dedicated 'current_answer' field, 
    # but we can look at the last history item if it's from user.
    
    history = state.get("history", [])
    if not history or history[-1]["role"] != "user":
        # Fallback or error, but assuming flow is correct
        user_answer = "No answer provided."
    else:
        user_answer = history[-1]["content"]
    
    # Check for exit handled in graph logic or main loop. 
    # But if we are here, we evaluate.
    
    if user_answer == "<SKIPPED>":
        new_evaluation = Evaluation(
            question=question,
            user_answer="Allowed to Skip.",
            score=0,
            feedback="Question skipped by candidate.",
            topics=state["topics"],
            complexity=state["complexity_level"]
        )
        logger.info("Question skipped by user")
    else:
        prompt = EVALUATION.format(
            question=question,
            user_answer=user_answer
        )

        llm = get_llm(temperature=config.TEMPERATURE_EVAL, max_tokens=config.MAX_TOKENS_EVAL)
        response = llm.invoke([HumanMessage(content=prompt)])
        eval_data = extract_json(response.content)

        new_evaluation = Evaluation(
            question=question,
            user_answer=user_answer,
            score=eval_data.get("score", 0),
            feedback=eval_data.get("feedback", "No feedback."),
            topics=state["topics"],
            complexity=state["complexity_level"]
        )
        logger.info(f"Answer evaluated. Score: {eval_data.get('score', 0)}")
    
    # Increase complexity

    new_complexity = min(state["complexity_level"] + 1, 10)
    
    return {
        "evaluations": [new_evaluation], # LangGraph will append specific to reducer if configured, or we assume overwrite/append list logic depends on State definition. 
        # In TypedDict with LangGraph, we typically need to manually merge or use Annotated.
        # For simple TypedDict state, we need to return the FULL list if it's a replacement,
        # OR we need to use `Annotated[List, add_messages]` style reducers.
        # Let's look at state.py again. It is a simple TypedDict. 
        # Default StateGraph behavior with TypedDict updates keys.
        # So we need to append manually.
        "evaluations": state.get("evaluations", []) + [new_evaluation],
        "complexity_level": new_complexity,
        "question_count": state.get("question_count", 0) + 1,
        "current_question": None
    }
