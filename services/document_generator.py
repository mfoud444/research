import os
import uuid
import subprocess
from typing import List, Tuple

class DocumentGenerator:
    def __init__(self, upload_folder):
        self.upload_folder = upload_folder
        os.makedirs(self.upload_folder, exist_ok=True)

    def generate_filename(self) -> Tuple[str, str]:
        """Generate filenames with unique ID"""
        unique_id = str(uuid.uuid4())[:8]
        md_filename = f"research_paper_{unique_id}.md"
        docx_filename = f"research_paper_{unique_id}.docx"
        return md_filename, docx_filename

    def convert_to_word(self, md_filename: str, docx_filename: str) -> None:
        """Convert markdown file to Word document using Pandoc"""
        md_path = os.path.join(self.upload_folder, md_filename)
        docx_path = os.path.join(self.upload_folder, docx_filename)
        
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