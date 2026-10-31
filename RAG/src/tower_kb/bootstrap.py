from tower_kb.adapters.database import Database
from tower_kb.application.document_service import DocumentService
from tower_kb.application.rag_service import RagService
from tower_kb.ingestion.pipeline import Pipeline

class Container:
    def __init__(self,settings):
        settings.validate()
        self.settings = settings
        self.db = Database(settings.data_dir / "knowledge.db")
        self.documents = DocumentService(self.db,settings.data_dir / "objects")
        self.pipeline = Pipeline(self.db,settings.data_dir / "objects")
        self.rag = RagService(self.db)
