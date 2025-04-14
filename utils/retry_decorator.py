import time
import random
from functools import wraps

def retry(max_retries=3, initial_delay=1, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        raise  # Re-raise the last exception if max retries reached
                    
                    # Exponential backoff with some randomness
                    time.sleep(delay + random.uniform(0, 0.5))
                    delay *= backoff_factor
        return wrapper
    return decorator