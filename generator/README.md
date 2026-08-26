# 3 · GENERATOR — Taha

Main task of application is to generate content based on record. 
The generator can create case_study depending on the specified parameters. 
The application leverages advanced algorithms and machine learning models to ensure high-quality and 
relevant content generation.

# How to start
paste to the terminal:
```bash
uvicorn generator.GeneratorController:app --reload --port 8001
```
You can check the api documentation at http://localhost:8001/docs
Make sure you have the required dependencies installed. You can install them using pip:
```bash
pip install -r requirements.txt
```

