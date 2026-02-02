MODEL_NAME = "meta-llama/Meta-Llama-3.1-8B-Instruct"
BASE_URL = "http://192.168.0.2:8000/v1"
API_KEY = "EMPTY"

TEMPERATURE_ASK = 0.7
TEMPERATURE_EVAL = 0.2
TEMPERATURE_RECOMMEND = 0.2

MAX_QUESTIONS_DEFAULT = 10

# HR recommendation thresholds (adjust as needed)
MOVE_FORWARD_SCORE = 7.5
HOLD_SCORE = 5.5
MIN_ELIGIBLE_RESUME_SCORE = 70

# LLM performance controls
MAX_TOKENS_QUESTION = 220
MAX_TOKENS_EVAL = 220
MAX_TOKENS_RECOMMEND = 350
LLM_TIMEOUT_SECONDS = 15

# Question bank mixing (for uploaded HR question list)
# Example: 2 means every 2nd question is from bank (if available)
BANK_ASK_EVERY = 2
