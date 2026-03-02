"""RAG vector store for HDL design patterns and best practices.

This module provides ChromaDB-based vector storage and retrieval for:
- HDL design patterns (FIFO, AXI, pipelines)
- Protocol specifications (AXI4-Lite, APB, etc.)
- Best practices (reset strategies, clock gating)
- Error patterns (common mistakes and fixes)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class RAGVectorStore:
    """ChromaDB-based vector store for HDL knowledge base."""
    
    def __init__(
        self,
        persist_directory: str = "data/rag/vector_db",
        collection_name: str = "hdl_design_patterns",
        embedding_model: str = "text-embedding-3-small",
    ):
        """Initialize the vector store.
        
        Args:
            persist_directory: Directory for ChromaDB persistence
            collection_name: Name of the collection to use
            embedding_model: OpenAI embedding model name
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb not installed. Run: pip install chromadb"
            )
        
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        
        # Ensure persist directory exists
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": "HDL design patterns and best practices",
                "embedding_model": embedding_model,
            }
        )
    
    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a single document to the vector store.
        
        Args:
            doc_id: Unique document identifier
            text: Document text content
            metadata: Optional metadata (tags, category, etc.)
        """
        self.collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )
    
    def add_documents(
        self,
        doc_ids: List[str],
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add multiple documents in batch.
        
        Args:
            doc_ids: List of document IDs
            texts: List of document texts
            metadatas: Optional list of metadata dicts
        """
        self.collection.add(
            ids=doc_ids,
            documents=texts,
            metadatas=metadatas or [{}] * len(doc_ids),
        )
    
    def search(
        self,
        query: str,
        n_results: int = 3,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar documents.
        
        Args:
            query: Search query text
            n_results: Number of results to return
            where: Metadata filters (e.g., {"category": "design_patterns"})
            where_document: Document content filters
        
        Returns:
            List of search results with documents, metadata, and distances
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            where_document=where_document,
        )
        
        # Format results
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                    "score": 1 - results["distances"][0][i] if results["distances"] else None,
                })
        
        return formatted
    
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID.
        
        Args:
            doc_id: Document identifier
        
        Returns:
            Document dict or None if not found
        """
        results = self.collection.get(ids=[doc_id])
        
        if results["ids"]:
            return {
                "id": results["ids"][0],
                "document": results["documents"][0],
                "metadata": results["metadatas"][0] if results["metadatas"] else {},
            }
        return None
    
    def delete_document(self, doc_id: str) -> None:
        """Delete a document by ID.
        
        Args:
            doc_id: Document identifier
        """
        self.collection.delete(ids=[doc_id])
    
    def count(self) -> int:
        """Get total number of documents in collection.
        
        Returns:
            Document count
        """
        return self.collection.count()
    
    def reset(self) -> None:
        """Delete all documents from the collection."""
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={
                "description": "HDL design patterns and best practices",
                "embedding_model": self.embedding_model,
            }
        )


class KnowledgeLoader:
    """Load and index knowledge documents into RAG vector store."""
    
    def __init__(self, persist_dir: str = "data/rag/vector_db"):
        """Initialize knowledge loader.
        
        Args:
            persist_dir: Directory for vector database persistence
        """
        self.vector_store = RAGVectorStore(persist_directory=persist_dir)
    
    def load_from_directory(
        self,
        docs_dir: str,
        extensions: List[str] = [".md", ".txt"],
    ) -> int:
        """Load all documents from a directory.
        
        Args:
            docs_dir: Path to knowledge documents directory
            extensions: File extensions to include
        
        Returns:
            Number of documents loaded
        """
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            raise FileNotFoundError(f"Directory not found: {docs_dir}")
        
        doc_ids = []
        texts = []
        metadatas = []
        
        for ext in extensions:
            for file_path in docs_path.rglob(f"*{ext}"):
                # Generate doc_id from relative path
                rel_path = file_path.relative_to(docs_path)
                doc_id = str(rel_path).replace(os.sep, "/").replace(ext, "")
                
                # Read document content
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Extract metadata from frontmatter if present
                metadata = self._extract_metadata(content, str(rel_path))
                
                doc_ids.append(doc_id)
                texts.append(content)
                metadatas.append(metadata)
        
        if doc_ids:
            self.vector_store.add_documents(doc_ids, texts, metadatas)
        
        return len(doc_ids)
    
    def _extract_metadata(self, content: str, file_path: str) -> Dict[str, Any]:
        """Extract metadata from document frontmatter.
        
        Args:
            content: Document content
            file_path: Relative file path
        
        Returns:
            Metadata dictionary
        """
        metadata = {"file_path": file_path}
        
        # Try to extract YAML frontmatter (between --- markers)
        if content.startswith("---"):
            try:
                end_marker = content.find("---", 3)
                if end_marker != -1:
                    frontmatter = content[3:end_marker].strip()
                    # Simple key-value parsing (not full YAML)
                    for line in frontmatter.split("\n"):
                        if ":" in line:
                            key, value = line.split(":", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            metadata[key] = value
            except Exception:
                pass  # Ignore parsing errors
        
        # Infer category from file path
        path_parts = file_path.split(os.sep)
        if len(path_parts) > 1:
            metadata["category"] = path_parts[0]
        
        return metadata
    
    def search(
        self,
        query: str,
        n_results: int = 3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar documents.
        
        Args:
            query: Search query
            n_results: Number of results
            filters: Metadata filters
        
        Returns:
            List of matching documents
        """
        return self.vector_store.search(query, n_results, where=filters)
    
    def build_index(self) -> int:
        """Build index from default knowledge docs directory.
        
        Returns:
            Number of documents indexed
        """
        docs_dir = "data/rag/knowledge_docs"
        if not os.path.exists(docs_dir):
            print(f"Warning: Knowledge docs directory not found: {docs_dir}")
            return 0
        
        return self.load_from_directory(docs_dir)
