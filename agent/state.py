from typing import TypedDict, List, Dict, Any, Optional

class Evaluation(TypedDict):
    question: str
    user_answer: str
    score: int
    feedback: str
    topics: List[str]
    complexity: str # e.g., "Beginner", "Intermediate", "Advanced"

class AgentState(TypedDict):
    topics: List[str]
    history: List[Dict[str, str]] # Chat history (user/assistant)
    current_question: Optional[str]
    evaluations: List[Evaluation]
    complexity_level: int # 1 to 10 or similar scale
    question_count: int
    exit_session: bool
    question_bank: List[str]
    bank_index: int
