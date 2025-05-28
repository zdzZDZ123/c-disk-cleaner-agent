import os
import json
from pathlib import Path

def get_data_path():
    """Get the path to the data directory."""
    return Path(__file__).parent

def load_data(filename):
    """Load data from a JSON file."""
    data_path = get_data_path()
    file_path = data_path / filename
    
    if not file_path.exists():
        return None
        
    with open(file_path, 'r') as f:
        return json.load(f)

def save_data(data, filename):
    """Save data to a JSON file."""
    data_path = get_data_path()
    file_path = data_path / filename
    
    with open(file_path, 'w') as f:
        json.dump(data, f) # Corrected: json.dump(data, f) instead of json.dump(data, file_path)