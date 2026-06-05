!pip install pydantic great-expectations pandas apscheduler tenacity loguru rich -q 

import importlib, subprocess 
for pkg in ["pydantic", "great_expectations", "apscheduler"]: 
  print(f"✓ {pkg} {importlib.import_module(pkg).__version__}")
