"""
Document management component for uploading and managing documents.
"""

import gradio as gr
from typing import List, Optional
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


def ingest_uploaded_file(file) -> str:
    """
    Ingest an uploaded file into the vector store.

    Args:
        file: Uploaded file object

    Returns:
        Status message
    """
    if file is None:
        return "No file uploaded."

    try:
        from src.ingestion.pipeline import IngestionPipeline

        pipeline = IngestionPipeline()

        # Get the file path
        file_path = file.name if hasattr(file, 'name') else str(file)

        result = pipeline.ingest_file(file_path)

        if result["success"]:
            return (
                f"✅ Successfully ingested: {result['document'].get('filename', 'Unknown')}\n"
                f"- Chunks created: {result['chunk_count']}\n"
                f"- Source ID: {result['document'].get('source_id', 'N/A')}"
            )
        else:
            return f"❌ Ingestion failed: {result['error']}"

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        return f"❌ Error: {str(e)}"


def ingest_text_content(text: str, source_name: str) -> str:
    """
    Ingest raw text content.

    Args:
        text: Text content to ingest
        source_name: Name for the source

    Returns:
        Status message
    """
    if not text.strip():
        return "No text provided."

    if not source_name.strip():
        source_name = "Manual Entry"

    try:
        from src.ingestion.pipeline import IngestionPipeline

        pipeline = IngestionPipeline()
        result = pipeline.ingest_text(text, source_name)

        if result["success"]:
            return (
                f"✅ Successfully ingested text: {source_name}\n"
                f"- Chunks created: {result['chunk_count']}\n"
                f"- Source ID: {result['source_id']}"
            )
        else:
            return f"❌ Ingestion failed: {result['error']}"

    except Exception as e:
        logger.error(f"Text ingestion error: {e}")
        return f"❌ Error: {str(e)}"


def get_document_list() -> List[List[str]]:
    """
    Get list of ingested documents.

    Returns:
        List of [filename, status, chunks] for table display
    """
    try:
        from src.retrieval.vector_store import VectorStore

        vs = VectorStore()
        stats = vs.get_collection_stats()

        # For now, return summary info
        return [[
            "All Documents",
            "Active",
            str(stats.get("total_documents", 0)),
        ]]
    except Exception as e:
        logger.error(f"Error getting document list: {e}")
        return [["Error", str(e), "0"]]


def search_knowledge_base(query: str, top_k: int) -> str:
    """
    Search the knowledge base.

    Args:
        query: Search query
        top_k: Number of results

    Returns:
        Formatted search results
    """
    if not query.strip():
        return "Please enter a search query."

    try:
        from src.retrieval.retriever import Retriever

        retriever = Retriever()
        results = retriever.retrieve(query, top_k=top_k)

        if not results:
            return "No results found."

        output = f"**Found {len(results)} results:**\n\n"

        for i, result in enumerate(results, 1):
            output += f"### [{i}] {result.source_name}\n"
            output += f"*Confidence: {result.similarity_score:.2f}*\n\n"
            output += f"{result.text[:500]}...\n\n"
            output += "---\n\n"

        return output

    except Exception as e:
        logger.error(f"Search error: {e}")
        return f"Error: {str(e)}"


def create_document_manager() -> gr.Blocks:
    """
    Create the document management component.

    Returns:
        Gradio Blocks component
    """
    with gr.Blocks() as doc_manager:
        gr.Markdown("## 📁 Document Management")
        gr.Markdown(
            "Upload agricultural documents (PDF, DOCX) to add them to the knowledge base."
        )

        with gr.Tabs():
            # Upload Tab
            with gr.TabItem("📤 Upload Documents"):
                with gr.Row():
                    with gr.Column():
                        file_upload = gr.File(
                            label="Upload Document",
                            file_types=[".pdf", ".docx"],
                            type="filepath",
                        )
                        upload_btn = gr.Button("Ingest Document", variant="primary")
                        upload_status = gr.Textbox(
                            label="Status",
                            interactive=False,
                            lines=4,
                        )

                    with gr.Column():
                        gr.Markdown("### Supported Formats")
                        gr.Markdown("""
                        - **PDF** (.pdf) - Agricultural guides, extension manuals
                        - **DOCX** (.docx) - Word documents

                        ### Tips
                        - Use documents from trusted sources (FAO, extension services)
                        - Ensure documents are text-based (not scanned images)
                        - Larger documents will create more chunks
                        """)

                upload_btn.click(
                    ingest_uploaded_file,
                    inputs=[file_upload],
                    outputs=[upload_status],
                )

            # Manual Text Entry Tab
            with gr.TabItem("✏️ Add Text"):
                gr.Markdown("### Add Text Content Directly")
                gr.Markdown("Paste agricultural information directly into the knowledge base.")

                text_name = gr.Textbox(
                    label="Source Name",
                    placeholder="e.g., 'Maize Fertilizer Guide'",
                )
                text_content = gr.Textbox(
                    label="Content",
                    placeholder="Paste your agricultural content here...",
                    lines=10,
                )
                text_btn = gr.Button("Add to Knowledge Base", variant="primary")
                text_status = gr.Textbox(label="Status", interactive=False)

                text_btn.click(
                    ingest_text_content,
                    inputs=[text_content, text_name],
                    outputs=[text_status],
                )

                # Example content
                gr.Markdown("### Example Content")
                example_text = """Maize Fertilizer Application Guidelines for East Africa:

1. **Planting Time Application:**
   - Apply DAP (Diammonium Phosphate) at 50 kg/ha at planting
   - Place fertilizer 5cm to the side and 5cm below the seed
   - Never place fertilizer in direct contact with seeds

2. **Top Dressing (V6-V8 Stage):**
   - Apply Urea at 50 kg/ha when maize is knee-high (6-8 leaves)
   - Apply during cool morning hours or evening
   - Avoid application if heavy rain is expected within 24 hours

3. **Signs of Nutrient Deficiency:**
   - Nitrogen: Yellowing of lower leaves, V-shaped pattern
   - Phosphorus: Purple coloration of leaves
   - Potassium: Browning of leaf edges

4. **Important Notes:**
   - Soil test recommended before application
   - Adjust rates based on previous crop and soil fertility
   - Split applications improve nutrient use efficiency"""

                def load_example():
                    return "Maize Fertilizer Guide - East Africa", example_text

                load_example_btn = gr.Button("Load Example")
                load_example_btn.click(
                    load_example,
                    outputs=[text_name, text_content],
                )

            # Search Tab
            with gr.TabItem("🔍 Search Knowledge Base"):
                gr.Markdown("### Search Indexed Documents")

                search_query = gr.Textbox(
                    label="Search Query",
                    placeholder="e.g., 'fertilizer application for maize'",
                )
                search_k = gr.Slider(
                    label="Number of Results",
                    minimum=1,
                    maximum=10,
                    value=5,
                    step=1,
                )
                search_btn = gr.Button("Search", variant="primary")
                search_results = gr.Markdown(label="Results")

                search_btn.click(
                    search_knowledge_base,
                    inputs=[search_query, search_k],
                    outputs=[search_results],
                )

            # Documents List Tab
            with gr.TabItem("📋 Document List"):
                gr.Markdown("### Indexed Documents")

                doc_table = gr.Dataframe(
                    headers=["Source", "Status", "Chunks"],
                    value=get_document_list(),
                    interactive=False,
                )

                refresh_docs_btn = gr.Button("Refresh List")
                refresh_docs_btn.click(
                    get_document_list,
                    outputs=[doc_table],
                )

    return doc_manager
