import logging
import sys
import os

def get_logger(name):
    logger = logging.getLogger(name)
    
    # If logger already has handlers, assume it's configured to avoid duplicate logs
    if logger.hasHandlers():
        return logger
        
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    # Ensure logs are saved in the root directory or a specific logs dir
    # We'll try to determine the project root relative to this file
    # This file is in agent/logger.py, so root is ../
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = os.path.join(project_root, 'interview_agent.log')
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}")
        
    return logger
