# pipeline/graph_generator.py
from dotenv import load_dotenv
load_dotenv()

import os
import json
import argparse
import yaml
from typing import Dict, Any
from tqdm import tqdm
from neo4j import GraphDatabase, exceptions

# --- Neo4j Database Connection Class ---

class GraphDatabaseConnection:
    """Manages the connection and queries to the Neo4j instance."""
    def __init__(self, uri, user, password, database):
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._driver = None
        try:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            self._driver.verify_connectivity()
            print("✅ Successfully connected to Neo4j.")
        except exceptions.AuthError:
            print("❌ Neo4j Authentication Error. Please check your credentials.")
            raise
        except Exception as e:
            print(f"❌ An unexpected error occurred during Neo4j driver initialization: {e}")
            raise

    def close(self):
        if self._driver:
            self._driver.close()

    def add_document_graph(self, doc_data: Dict[str, Any]):
        """
        Adds a document and its pages, entities, and relationships to the graph.
        """
        doc_id = doc_data.get("document_id")
        source_file = doc_data.get("source_file")

        with self._driver.session(database=self._database) as session:
            # 1. Create or merge the Document node
            session.run(
                "MERGE (d:Document {id: $doc_id}) SET d.source_file = $source_file",
                doc_id=doc_id,
                source_file=source_file
            )

            # 2. Iterate through pages and create nodes and relationships
            for page in doc_data.get("pages", []):
                page_num = page.get("page_number")
                page_meta = page.get("page_metadata", {})
                page_id = f"{doc_id}_page_{page_num}"

                # Create Page node and link to Document
                session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    MERGE (p:Page {id: $page_id})
                    SET p.page_number = $page_num, p.summary = $summary, p.content_type = $content_type
                    MERGE (d)-[:HAS_PAGE]->(p)
                    """,
                    doc_id=doc_id,
                    page_id=page_id,
                    page_num=page_num,
                    summary=page_meta.get("summary"),
                    content_type=page_meta.get("content_type")
                )

                # 3. Create Entity nodes and link them to the Page
                for entity_name in page_meta.get("entities", []):
                    if entity_name: # Ensure entity is not an empty string
                        session.run(
                            """
                            MATCH (p:Page {id: $page_id})
                            MERGE (e:Entity {name: $entity_name})
                            MERGE (p)-[:MENTIONS]->(e)
                            """,
                            page_id=page_id,
                            entity_name=entity_name
                        )

# --- Path Resolution Function ---
def resolve_paths(config: Dict):
    """Resolves path placeholders in the config."""
    paths = config['paths']
    output_base = paths.get('output_base', '')
    for key, val in list(paths.items()):
        if isinstance(val, str):
            paths[key] = val.replace('{paths.output_base}', output_base)
    return config

# --- Main Pipeline Logic ---

def run_graph_pipeline(config: Dict):
    paths = config['paths']
    
    try:
        graph_db = GraphDatabaseConnection(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USERNAME"),
            password=os.getenv("NEO4J_PASSWORD"),
            database=os.getenv("NEO4J_DATABASE")
        )
    except Exception as e:
        print(f"Could not initialize graph database connection: {e}. Exiting.")
        return

    processed_json_dir = paths['processed_json']
    if not os.path.isdir(processed_json_dir):
        print(f"❌ Processed JSON directory not found at '{processed_json_dir}'.")
        return
        
    json_files = [f for f in os.listdir(processed_json_dir) if f.endswith('.json')]
    
    print(f"Found {len(json_files)} processed documents to build graph from.")

    for file_name in tqdm(json_files, desc="Building Knowledge Graph", unit="doc"):
        file_path = os.path.join(processed_json_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                document_data = json.load(f)
            
            graph_db.add_document_graph(document_data)

        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {file_name}. Skipping.")
            continue
        except Exception as e:
            print(f"Error processing file {file_name}: {e}")

    graph_db.close()
    print("\n✅ Knowledge Graph pipeline complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build a knowledge graph from processed documents.")
    parser.add_argument("--config", default="config.yaml", help="Path to the config.yaml file.")
    args = parser.parse_args()

    try:
        with open(args.config, 'r') as file:
            config = yaml.safe_load(file)
        
        config = resolve_paths(config)
        run_graph_pipeline(config)
    except FileNotFoundError:
        print(f"❌ Error: Config file not found at '{args.config}'")
    except Exception as e:
        print(f"🔥 An unexpected error occurred in main execution: {e}")
