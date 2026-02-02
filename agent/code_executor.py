import requests
import json

PISTON_API_URL = "https://emkc.org/api/v2/piston"

def get_runtimes():
    """Fetch available languages from Piston."""
    try:
        response = requests.get(f"{PISTON_API_URL}/runtimes")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching runtimes: {e}")
        return []

def execute_code(language, code, stdin=""):
    """
    Execute code using Piston API.
    language: str (e.g., 'python', 'javascript')
    code: str
    stdin: str (Input for the program)
    """
    # Map common names to Piston versions if needed, or rely on wildcard
    payload = {
        "language": language,
        "version": "*",
        "files": [
            {
                "content": code
            }
        ],
        "stdin": stdin
    }
    
    try:
        response = requests.post(f"{PISTON_API_URL}/execute", json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"run": {"output": f"Error executing code: {e}", "code": -1}}

def run_test_cases(language, code, test_cases):
    """
    Run code against a list of test cases.
    test_cases: List[Dict] -> [{'input': '...', 'output': '...'}]
    
    Returns:
    {
        "passed": int,
        "total": int,
        "results": List[Dict] # Details per test case
        "full_output": str # Combined output log
    }
    """
    results = []
    passed = 0
    full_output = ""
    
    for i, test in enumerate(test_cases, 1):
        stdin = test.get("input", "")
        expected = test.get("output", "").strip()
        
        exec_result = execute_code(language, code, stdin)
        
        run_data = exec_result.get("run", {})
        actual_output = run_data.get("stdout", "").strip()
        stderr = run_data.get("stderr", "")
        exit_code = run_data.get("code", 0)
        
        # Simple string comparison (could be improved)
        is_correct = (actual_output == expected) and (exit_code == 0)
        
        if is_correct:
            passed += 1
            status = "✅ Passed"
        else:
            status = "❌ Failed"
            
        result_entry = {
            "test_case": i,
            "input": stdin,
            "expected": expected,
            "actual": actual_output,
            "error": stderr,
            "status": status
        }
        results.append(result_entry)
        
        full_output += f"Test Case {i}: {status}\nInput: {stdin}\nExpected: {expected}\nActual: {actual_output}\nError: {stderr}\n\n"

    return {
        "passed": passed,
        "total": len(test_cases),
        "results": results,
        "full_output": full_output
    }
