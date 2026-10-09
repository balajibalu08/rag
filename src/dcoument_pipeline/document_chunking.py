import json
import re
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter


# 1. CONFIGURATION


INPUT_JSON = "./data/raw_files/extracted_data.json"
OUTPUT_JSON = "./data/chunks/chunks.json"


headers_to_split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]



# 2. LOAD EXTRACTED JSON



def load_extracted_data(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)



# 3. CONVERT HEADING TO MARKDOWN



def heading_to_markdown(text):
    """
    Examples:

    1. Academic Regulations
        -> # 1. Academic Regulations

    2.1 Programmes Offered
        -> ## 2.1 Programmes Offered

    2.1.1 Computer Science
        -> ### 2.1.1 Computer Science
    """

    text = text.strip()

    match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+", text)

    if match:
        number = match.group(1)

        # Determine heading level from numbering
        level = len(number.split("."))

        # We support H1, H2 and H3
        level = min(level, 3)

        return f"{'#' * level} {text}"

    # If heading has no numbering
    return f"# {text}"



# 4. CONVERT ONE DOCUMENT'S ELEMENTS TO MARKDOWN



def elements_to_markdown(elements):
    markdown_parts = []

    for element in elements:
        element_type = element["type"]
        content = element["content"].strip()

        if not content:
            continue

        
        # TITLE / HEADING
        

        if element_type in ["title", "heading"]:
            markdown_parts.append(heading_to_markdown(content))

        
        # PARAGRAPH
        

        elif element_type == "paragraph":
            markdown_parts.append(content)

        
        # LIST ITEM
        

        elif element_type == "list_item":
            markdown_parts.append(f"- {content}")

        
        # TABLE
        

        elif element_type == "table":
            # Docling already gave us Markdown table
            markdown_parts.append(content)

        
        # CAPTION
        

        elif element_type == "caption":
            markdown_parts.append(content)

        
        # CODE
        

        elif element_type == "code":
            markdown_parts.append(f"```\n{content}\n```")

        
        # PICTURE
        

        elif element_type == "picture":
            markdown_parts.append(content)

        
        # DOCUMENT INDEX
        

        elif element_type == "document_index":
            # Don't use table of contents as RAG knowledge
            continue

        # Separate elements
        markdown_parts.append("")

    return "\n".join(markdown_parts)



# 5. CHUNK ONE DOCUMENT



def chunk_document(document):
    markdown_parts = []
    element_map = []

    
    # Convert JSON elements to Markdown
    

    for element in document["elements"]:
        element_type = element["type"]
        content = element["content"].strip()

        if not content:
            continue

        # Ignore document index
        if element_type == "document_index":
            continue

        # Convert heading/title
        if element_type in ["title", "heading"]:
            markdown_content = heading_to_markdown(content)

        # List item
        elif element_type == "list_item":
            markdown_content = f"- {content}"

        # Table
        elif element_type == "table":
            markdown_content = content

        # Everything else
        else:
            markdown_content = content

        markdown_parts.append(markdown_content)
        markdown_parts.append("")

        # Keep original element information
        element_map.append(
            {
                "element_id": element["element_id"],
                "page_number": element["page_number"],
                "type": element_type,
                "section_path": element.get("section_path", []),
                "content": markdown_content,
            }
        )

    
    # Create Markdown
    

    markdown_text = "\n".join(markdown_parts)

    
    # Header-based splitting
    

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )

    chunks = splitter.split_text(markdown_text)

    final_chunks = []

    
    # Recover metadata for each chunk
    

    for chunk_index, chunk in enumerate(chunks):
        chunk_content = chunk.page_content.strip()

        matched_elements = []

        # Find original elements whose content
        # appears inside this chunk
        for element in element_map:
            element_content = element["content"].strip()

            if not element_content:
                continue

            if element_content in chunk_content:
                matched_elements.append(element)

        
        # Collect metadata
        

        element_ids = list(
            dict.fromkeys(element["element_id"] for element in matched_elements)
        )

        page_numbers = sorted(
            set(element["page_number"] for element in matched_elements)
        )

        content_types = list(
            dict.fromkeys(element["type"] for element in matched_elements)
        )

        # Use the section path from the deepest/latest
        # matching element
        section_path = []

        if matched_elements:
            section_path = matched_elements[-1].get("section_path", [])

        
        # Create final chunk
        

        final_chunks.append(
            {
                "chunk_id": (
                    f"{Path(document['file_name']).stem}_chunk_{chunk_index + 1}"
                ),
                "document_name": document["file_name"],
                "content": chunk_content,
                "metadata": {
                    "source": document["file_name"],
                    "section_path": section_path,
                    "page_numbers": page_numbers,
                    "element_ids": element_ids,
                    "content_types": content_types,
                    "headers": chunk.metadata,
                },
            }
        )

    return final_chunks



# 6. CHUNK ALL DOCUMENTS



def create_chunks(input_json, output_json):

    documents = load_extracted_data(input_json)

    all_chunks = []

    for document in documents:
        print(f"Chunking: {document['file_name']}")

        document_chunks = chunk_document(document)

        all_chunks.extend(document_chunks)

        print(f"Created {len(document_chunks)} chunks")

    # Create output directory
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save chunks
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print()
    print(f"Total chunks: {len(all_chunks)}")

    print(f"Saved to: {output_path.resolve()}")

    return all_chunks



# 7. RUN


if __name__ == "__main__":
    chunks = create_chunks(input_json=INPUT_JSON, output_json=OUTPUT_JSON)
