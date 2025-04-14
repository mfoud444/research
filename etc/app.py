
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, copy_current_request_context
import g4f
import os
import subprocess
from datetime import datetime
from typing import List, Tuple
import uuid
from werkzeug.utils import secure_filename
import json
import time
from functools import wraps

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'output'

from functools import wraps
import time
import random

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
# Initialize output directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_available_models() -> List[str]:
    """Get list of available models from g4f"""
    try:
        models = sorted(g4f.models._all_models)
        # Ensure gpt-4o is first if available
        if 'gpt-4o' in models:
            models.remove('gpt-4o')
            models.insert(0, 'gpt-4o')
        return models
    except Exception:
        return ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo', 'llama2-70b', 'claude-2']
    
def generate_filename() -> Tuple[str, str]:
    """Generate filenames with unique ID"""
    unique_id = str(uuid.uuid4())[:8]
    md_filename = f"research_paper_{unique_id}.md"
    docx_filename = f"research_paper_{unique_id}.docx"
    return md_filename, docx_filename

def generate_index_content(model: str, research_subject: str, manual_chapters: List[str] = None) -> str:
    """Generate index content for the research paper"""
    try:
        if manual_chapters:
            prompt = f"Generate a detailed index/table of contents for a research paper about {research_subject} with these chapters: " + \
                    ", ".join(manual_chapters) + ". Include section headings in markdown format."
        else:
            prompt = f"Generate a detailed index/table of contents for a research paper about {research_subject}. Include chapter titles and section headings in markdown format."
        
        response = g4f.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(response) if response else "[Empty response from model]"
    except Exception as e:
        raise Exception(f"Failed to generate index: {str(e)}")

def extract_chapters(index_content: str) -> List[str]:
    """Extract chapter titles from index content"""
    chapters = []
    for line in index_content.split('\n'):
        if line.strip().startswith('## '):
            chapter_title = line.strip()[3:].strip()
            if chapter_title.lower() not in ['introduction', 'conclusion', 'references']:
                chapters.append(chapter_title)
    return chapters if chapters else ["Literature Review", "Methodology", "Results and Discussion"]

def generate_automatic_sections(model: str, research_subject: str) -> List[Tuple[str, str]]:
    """Generate sections automatically based on AI-generated index"""
    try:
        index_content = generate_index_content(model, research_subject)
        chapters = extract_chapters(index_content)
        
        sections = [
            ("Index", index_content),
            ("Introduction", f"Write a comprehensive introduction for a research paper about {research_subject}. Include background information, research objectives, and significance of the study.")
        ]
        
        for i, chapter in enumerate(chapters, 1):
            sections.append(
                (f"Chapter {i}: {chapter}", 
                 f"Write a detailed chapter about '{chapter}' for a research paper about {research_subject}. "
                 f"Provide comprehensive coverage of this aspect, including relevant theories, examples, and analysis.")
            )
        
        sections.append(
            ("Conclusion", f"Write a conclusion section for a research paper about {research_subject}. Summarize key findings, discuss implications, and suggest future research directions.")
        )
        
        return sections
    except Exception as e:
        raise Exception(f"Failed to generate automatic structure: {str(e)}")

def get_manual_sections(research_subject: str) -> List[Tuple[str, str]]:
    """Get predefined manual sections"""
    return [
        ("Index", "[Index will be generated first]"),
        ("Introduction", f"Write a comprehensive introduction for a research paper about {research_subject}."),
        ("Chapter 1: Literature Review", f"Create a detailed literature review chapter about {research_subject}."),
        ("Chapter 2: Methodology", f"Describe the research methodology for a study about {research_subject}."),
        ("Chapter 3: Results and Discussion", f"Present hypothetical results and discussion for a research paper about {research_subject}. Analyze findings and compare with existing literature."),
        ("Conclusion", f"Write a conclusion section for a research paper about {research_subject}.")
    ]

@retry(max_retries=3, initial_delay=1, backoff_factor=2)
def generate_section_content(model: str, prompt: str) -> str:
    """Generate content for a single section with retry logic"""
    try:
        response = g4f.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=False  # Disable streaming to avoid async issues
        )
        return str(response) if response else "[Empty response from model]"
    except Exception as e:
        raise Exception(f"Failed to generate section content: {str(e)}")

def write_research_paper(md_filename: str, research_subject: str, sections: List[Tuple[str, str]], model: str) -> None:
    """Write the research paper to a markdown file"""
    full_path = os.path.join(app.config['UPLOAD_FOLDER'], md_filename)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(f"# Research Paper: {research_subject}\n\n")
        
        for section_title, prompt in sections:
            try:
                if isinstance(prompt, str) and (prompt.startswith("##") or prompt.startswith("#")):
                    content = f"{prompt}\n\n"
                else:
                    response = generate_section_content(model, prompt)
                    content = f"## {section_title}\n\n{response}\n\n"
                f.write(content)
            except Exception as e:
                f.write(f"## {section_title}\n\n[Error generating this section: {str(e)}]\n\n")

def convert_to_word(md_filename: str, docx_filename: str) -> None:
    """Convert markdown file to Word document using Pandoc"""
    md_path = os.path.join(app.config['UPLOAD_FOLDER'], md_filename)
    docx_path = os.path.join(app.config['UPLOAD_FOLDER'], docx_filename)
    
    command = [
        "pandoc", md_path,
        "-o", docx_path,
        "--standalone",
        "--table-of-contents",
        "--toc-depth=3"
    ]
    
    if os.path.exists("reference.docx"):
        command.extend(["--reference-doc", "reference.docx"])
    
    subprocess.run(command, check=True)

@app.route('/')
def index():
    models = get_available_models()
    return render_template('index.html', models=models)

def sse_stream_required(f):
    """Decorator to ensure SSE stream has request context"""
    @wraps(f)
    def decorated(*args, **kwargs):
        @copy_current_request_context
        def generator():
            return f(*args, **kwargs)
        return generator()
    return decorated

@app.route('/stream')
@sse_stream_required
def stream():
    research_subject = request.args.get('subject', '').strip()
    selected_model = request.args.get('model', 'gpt-4o')
    structure_type = request.args.get('structure', 'automatic')

    def generate():
        try:
            if not research_subject:
                yield "data: " + json.dumps({"error": "Research subject is required"}) + "\n\n"
                return
            
            # Generate filenames
            md_filename, docx_filename = generate_filename()
            
            # Initial steps
            steps = [
                {"id": 0, "text": "Preparing document structure...", "status": "pending"},
                {"id": 1, "text": "Generating index/table of contents...", "status": "pending"},
                {"id": 2, "text": "Determining chapters...", "status": "pending"},
                {"id": 3, "text": "Writing content...", "status": "pending", "subSteps": []},
                {"id": 4, "text": "Finalizing document...", "status": "pending"},
                {"id": 5, "text": "Converting to Word format...", "status": "pending"}
            ]
            
            # Initial progress update
            yield "data: " + json.dumps({"steps": steps, "progress": 0}) + "\n\n"
            
            # Step 0: Prepare
            steps[0]["status"] = "in-progress"
            yield "data: " + json.dumps({
                "steps": steps,
                "progress": 0,
                "current_step": 0
            }) + "\n\n"
            
            sections = []
            chapter_steps = []
            
            if structure_type == 'automatic':
                try:
                    # Step 1: Generate index
                    steps[1]["status"] = "in-progress"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 10,
                        "current_step": 1
                    }) + "\n\n"
                    
                    index_content = generate_index_content(selected_model, research_subject)
                    sections.append(("Index", index_content))
                    
                    steps[1]["status"] = "complete"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 20,
                        "current_step": 1
                    }) + "\n\n"
                    
                    # Step 2: Determine chapters
                    steps[2]["status"] = "in-progress"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 30,
                        "current_step": 2
                    }) + "\n\n"
                    
                    chapters = extract_chapters(index_content)
                    
                    # Create sub-steps for each chapter with initial timing info
                    chapter_substeps = [
                        {
                            "id": f"chapter_{i}", 
                            "text": chapter, 
                            "status": "pending",
                            "start_time": None,
                            "duration": None
                        }
                        for i, chapter in enumerate(chapters)
                    ]
                    
                    steps[3]["subSteps"] = chapter_substeps
                    
                    steps[2]["status"] = "complete"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 40,
                        "current_step": 2,
                        "update_steps": True
                    }) + "\n\n"
                    
                    # Add introduction and conclusion
                    sections.append((
                        "Introduction", 
                        f"Write a comprehensive introduction for a research paper about {research_subject}."
                    ))
                    
                    for i, chapter in enumerate(chapters, 1):
                        sections.append((
                            f"Chapter {i}: {chapter}", 
                            f"Write a detailed chapter about '{chapter}' for a research paper about {research_subject}."
                        ))
                    
                    sections.append((
                        "Conclusion",
                        f"Write a conclusion section for a research paper about {research_subject}."
                    ))
                    
                    # Generate content for each chapter with timing
                    for i, chapter in enumerate(chapters):
                        # Update chapter start time
                        steps[3]["subSteps"][i]["start_time"] = time.time()
                        steps[3]["subSteps"][i]["status"] = "in-progress"
                        
                        yield "data: " + json.dumps({
                            "steps": steps,
                            "progress": 40 + (i * 50 / len(chapters)),
                            "current_step": 3,
                            "chapter_progress": {
                                "current": i + 1,
                                "total": len(chapters),
                                "chapter": chapter,
                                "percent": ((i + 1) / len(chapters)) * 100
                            }
                        }) + "\n\n"
                        
                        try:
                            response = generate_section_content(
                                selected_model,
                                f"Write a detailed chapter about '{chapter}' for a research paper about {research_subject}."
                            )
                            
                            # Calculate and store duration
                            duration = time.time() - steps[3]["subSteps"][i]["start_time"]
                            steps[3]["subSteps"][i]["duration"] = f"{duration:.1f}s"
                            steps[3]["subSteps"][i]["status"] = "complete"
                            
                            yield "data: " + json.dumps({
                                "steps": steps,
                                "progress": 40 + ((i + 1) * 50 / len(chapters)),
                                "current_step": 3,
                                "chapter_progress": {
                                    "current": i + 1,
                                    "total": len(chapters),
                                    "chapter": chapter,
                                    "percent": ((i + 1) / len(chapters)) * 100,
                                    "duration": f"{duration:.1f}s"
                                }
                            }) + "\n\n"
                        except Exception as e:
                            duration = time.time() - steps[3]["subSteps"][i]["start_time"]
                            steps[3]["subSteps"][i]["duration"] = f"{duration:.1f}s"
                            steps[3]["subSteps"][i]["status"] = "error"
                            steps[3]["subSteps"][i]["message"] = str(e)
                            
                            yield "data: " + json.dumps({
                                "steps": steps,
                                "progress": 40 + ((i + 1) * 50 / len(chapters)),
                                "current_step": 3,
                                "warning": f"Failed to generate chapter {i+1} after retries",
                                "chapter_progress": {
                                    "current": i + 1,
                                    "total": len(chapters),
                                    "chapter": chapter,
                                    "percent": ((i + 1) / len(chapters)) * 100,
                                    "error": str(e)
                                }
                            }) + "\n\n"
                    
                    steps[3]["status"] = "complete"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 90,
                        "current_step": 3,
                        "chapter_progress": {
                            "complete": True,
                            "total_chapters": len(chapters)
                        }
                    }) + "\n\n"
                    
                except Exception as e:
                    steps[1]["status"] = "error"
                    steps[1]["message"] = str(e)
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 20,
                        "current_step": 1
                    }) + "\n\n"
                    
                    # Fallback to manual structure
                    sections = get_manual_sections(research_subject)
                    steps[1]["message"] = "Falling back to manual structure"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 20,
                        "current_step": 1
                    }) + "\n\n"
                    
                    try:
                        index_content = generate_index_content(selected_model, research_subject, [s[0] for s in sections[1:]])
                        sections[0] = ("Index", index_content)
                        
                        steps[1]["status"] = "complete"
                        yield "data: " + json.dumps({
                            "steps": steps,
                            "progress": 25,
                            "current_step": 1
                        }) + "\n\n"
                    except Exception as e:
                        steps[1]["status"] = "error"
                        steps[1]["message"] = str(e)
                        yield "data: " + json.dumps({
                            "steps": steps,
                            "progress": 20,
                            "current_step": 1,
                            "error": "Failed to generate even fallback content"
                        }) + "\n\n"
                        return
            else:
                sections = get_manual_sections(research_subject)
                steps[1]["status"] = "in-progress"
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 10,
                    "current_step": 1
                }) + "\n\n"
                
                try:
                    index_content = generate_index_content(selected_model, research_subject, [s[0] for s in sections[1:]])
                    sections[0] = ("Index", index_content)
                    
                    steps[1]["status"] = "complete"
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 20,
                        "current_step": 1
                    }) + "\n\n"
                except Exception as e:
                    steps[1]["status"] = "error"
                    steps[1]["message"] = str(e)
                    yield "data: " + json.dumps({
                        "steps": steps,
                        "progress": 20,
                        "current_step": 1,
                        "error": "Failed to generate manual index"
                    }) + "\n\n"
                    return
            
            # Write introduction
            steps[3]["status"] = "in-progress"
            yield "data: " + json.dumps({
                "steps": steps,
                "progress": 40,
                "current_step": 3
            }) + "\n\n"
            
            try:
                introduction_content = generate_section_content(
                    selected_model,
                    f"Write a comprehensive introduction for a research paper about {research_subject}."
                )
                
                steps[3]["status"] = "complete"
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 60,
                    "current_step": 3
                }) + "\n\n"
            except Exception as e:
                steps[3]["status"] = "error"
                steps[3]["message"] = str(e)
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 60,
                    "current_step": 3,
                    "warning": "Failed to generate introduction after retries"
                }) + "\n\n"
            
            # Write conclusion
            steps[4]["status"] = "in-progress"
            yield "data: " + json.dumps({
                "steps": steps,
                "progress": 80,
                "current_step": 4
            }) + "\n\n"
            
            try:
                conclusion_content = generate_section_content(
                    selected_model,
                    f"Write a conclusion section for a research paper about {research_subject}."
                )
                
                steps[4]["status"] = "complete"
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 90,
                    "current_step": 4
                }) + "\n\n"
            except Exception as e:
                steps[4]["status"] = "error"
                steps[4]["message"] = str(e)
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 90,
                    "current_step": 4,
                    "warning": "Failed to generate conclusion after retries"
                }) + "\n\n"
            
            # Write the complete paper
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], md_filename)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(f"# Research Paper: {research_subject}\n\n")
                
                for section_title, prompt in sections:
                    try:
                        if isinstance(prompt, str) and (prompt.startswith("##") or prompt.startswith("#")):
                            content = f"{prompt}\n\n"
                        else:
                            try:
                                response = generate_section_content(selected_model, prompt)
                                content = f"## {section_title}\n\n{response}\n\n"
                            except Exception as e:
                                content = f"## {section_title}\n\n[Error generating this section: {str(e)}]\n\n"
                        f.write(content)
                    except Exception as e:
                        f.write(f"## {section_title}\n\n[Error generating this section: {str(e)}]\n\n")
            
            # Convert to Word
            steps[5]["status"] = "in-progress"
            yield "data: " + json.dumps({
                "steps": steps,
                "progress": 95,
                "current_step": 5
            }) + "\n\n"
            
            try:
                convert_to_word(md_filename, docx_filename)
                steps[5]["status"] = "complete"
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 100,
                    "current_step": 5,
                    "status": "complete",
                    "docx_file": docx_filename,
                    "md_file": md_filename
                }) + "\n\n"
            except Exception as e:
                steps[5]["status"] = "error"
                steps[5]["message"] = str(e)
                yield "data: " + json.dumps({
                    "steps": steps,
                    "progress": 100,
                    "current_step": 5,
                    "status": "partial_success",
                    "message": f'Paper generated but Word conversion failed: {str(e)}',
                    "md_file": md_filename
                }) + "\n\n"
            
        except Exception as e:
            yield "data: " + json.dumps({"error": f"Failed to generate paper: {str(e)}"}) + "\n\n"
    
    return Response(generate(), mimetype="text/event-stream")

@app.route('/download/<filename>')
def download(filename):
    safe_filename = secure_filename(filename)
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        safe_filename,
        as_attachment=True
    )

if __name__ == '__main__':
    app.run(debug=True)