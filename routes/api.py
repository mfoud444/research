from typing import List, Tuple
from flask import Blueprint, jsonify, request, Response, send_from_directory, copy_current_request_context, abort, g
from functools import wraps
import time
import json
import os
import uuid
import random
from werkzeug.utils import secure_filename
from services.model_provider import ModelProvider
from services.document_generator import DocumentGenerator
from config import Config
from utils.retry_decorator import retry
import threading

api_bp = Blueprint('api', __name__)
model_provider = ModelProvider()
doc_generator = DocumentGenerator(Config.UPLOAD_FOLDER)
_generation_tasks = {}

def sse_stream_required(f):
    """Decorator to ensure SSE stream has request context"""
    @wraps(f)
    def decorated(*args, **kwargs):
        @copy_current_request_context
        def generator():
            return f(*args, **kwargs)
        return generator()
    return decorated

def extract_chapters(index_content: str) -> List[str]:
    """Extract chapter titles from index content"""
    chapters = []
    for line in index_content.split('\n'):
        if line.strip().startswith('## '):
            chapter_title = line.strip()[3:].strip()
            if chapter_title.lower() not in ['introduction', 'conclusion', 'references']:
                chapters.append(chapter_title)
    return chapters if chapters else ["Literature Review", "Methodology", "Results and Discussion"]

def generate_automatic_sections(model: str, research_subject: str, chapter_count: str = 'auto', 
                              word_count: str = 'auto', include_references: bool = False, 
                              citation_style: str = None) -> List[Tuple[str, str]]:
    """Generate sections automatically based on AI-generated index"""
    try:
        # Generate index with specified parameters
        index_prompt = f"Create a research paper outline about {research_subject}"
        if chapter_count != 'auto':
            index_prompt += f" with exactly {chapter_count} main chapters"
        if word_count != 'auto':
            index_prompt += f" targeting approximately {word_count} words"
        
        index_content = model_provider.generate_index_content(model, index_prompt)
        chapters = extract_chapters(index_content)
        
        # If specific chapter count requested, adjust chapters list
        if chapter_count != 'auto':
            requested_count = int(chapter_count)
            if len(chapters) > requested_count:
                chapters = chapters[:requested_count]
            elif len(chapters) < requested_count:
                default_chapters = ["Literature Review", "Methodology", "Results", "Discussion"]
                chapters.extend(default_chapters[len(chapters):requested_count])
        
        sections = [
            ("Index", index_content),
            ("Introduction", f"Write a comprehensive introduction for a research paper about {research_subject}. "
                           f"{'Target word count: ' + word_count + ' words.' if word_count != 'auto' else ''}")
        ]
        
        # Add chapter prompts
        for i, chapter in enumerate(chapters, 1):
            word_guidance = f" Target approximately {int(int(word_count) / (len(chapters) + 2)) } words." if word_count != 'auto' else ''
            sections.append(
                (f"Chapter {i}: {chapter}", 
                 f"Write a detailed chapter about '{chapter}' for a research paper about {research_subject}. "
                 f"Provide comprehensive coverage of this aspect, including relevant theories, examples, and analysis.{word_guidance}")
            )
        
        sections.append(
            ("Conclusion", f"Write a conclusion section for a research paper about {research_subject}.")
        )
        
        # Add references section if requested
        if include_references:
            sections.append(
                ("References", f"Generate a references section in {citation_style} format for this research paper about {research_subject}.")
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

def write_research_paper(md_filename: str, research_subject: str, sections: List[Tuple[str, str]], model: str) -> None:
    """Write the research paper to a markdown file"""
    full_path = os.path.join(Config.UPLOAD_FOLDER, md_filename)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(f"# Research Paper: {research_subject}\n\n")
        
        for section_title, prompt in sections:
            try:
                if isinstance(prompt, str) and (prompt.startswith("##") or prompt.startswith("#")):
                    content = f"{prompt}\n\n"
                else:
                    response = model_provider.generate_content(model, prompt)
                    content = f"## {section_title}\n\n{response}\n\n"
                f.write(content)
            except Exception as e:
                f.write(f"## {section_title}\n\n[Error generating this section: {str(e)}]\n\n")

@api_bp.route('/models')
def get_models():
    models = model_provider.get_available_models()
    return jsonify(models)

@api_bp.route('/stream')
@sse_stream_required
def stream():
    research_subject = request.args.get('subject', '').strip()
    selected_model = request.args.get('model', 'gpt-4o')
    structure_type = request.args.get('structure', 'automatic')
    chapter_count = request.args.get('chapterCount', 'auto')
    word_count = request.args.get('wordCount', 'auto')
    include_references = request.args.get('includeReferences') == 'true'
    citation_style = request.args.get('citationStyle')

    # Generate unique task ID
    task_id = str(uuid.uuid4())
    _generation_tasks[task_id] = {'abort': False}

    def generate():
        try:
            # Send task ID to client
            yield "data: " + json.dumps({"task_id": task_id}) + "\n\n"

            if not research_subject:
                yield "data: " + json.dumps({"error": "Research subject is required"}) + "\n\n"
                return
            
            # Generate filenames
            md_filename, docx_filename = doc_generator.generate_filename()
            
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
                    
                    sections = generate_automatic_sections(
                        selected_model, 
                        research_subject,
                        chapter_count,
                        word_count,
                        include_references,
                        citation_style
                    )
                    
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
                    
                    chapters = extract_chapters(sections[0][1])
                    
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
                            response = model_provider.generate_content(
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
                        index_content = model_provider.generate_index_content(selected_model, research_subject, [s[0] for s in sections[1:]])
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
                    index_content = model_provider.generate_index_content(selected_model, research_subject, [s[0] for s in sections[1:]])
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
                introduction_content = model_provider.generate_content(
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
                conclusion_content = model_provider.generate_content(
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
            write_research_paper(md_filename, research_subject, sections, selected_model)
            
            # Convert to Word
            steps[5]["status"] = "in-progress"
            yield "data: " + json.dumps({
                "steps": steps,
                "progress": 95,
                "current_step": 5
            }) + "\n\n"
            
            try:
                doc_generator.convert_to_word(md_filename, docx_filename)
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
            
            # Clean up task when done
            if task_id in _generation_tasks:
                del _generation_tasks[task_id]

        except Exception as e:
            # Clean up task on error
            if task_id in _generation_tasks:
                del _generation_tasks[task_id]
            if str(e) == "Generation aborted by user":
                yield "data: " + json.dumps({"status": "aborted"}) + "\n\n"
            else:
                yield "data: " + json.dumps({"error": f"Failed to generate paper: {str(e)}"}) + "\n\n"
    
    return Response(generate(), mimetype="text/event-stream")

@api_bp.route('/download/<filename>')
def download(filename):
    safe_filename = secure_filename(filename)
    return send_from_directory(
        Config.UPLOAD_FOLDER,
        safe_filename,
        as_attachment=True
    )

@api_bp.route('/abort/<task_id>', methods=['POST'])
def abort_generation(task_id):
    """Abort an ongoing generation task"""
    if task_id in _generation_tasks:
        _generation_tasks[task_id]['abort'] = True
        return jsonify({'status': 'aborted'})
    return jsonify({'status': 'not_found'}), 404
    