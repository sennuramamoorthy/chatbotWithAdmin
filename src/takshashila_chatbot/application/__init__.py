"""Application layer — orchestration and the ports to external systems.

Depends on ``domain`` (pure logic) and on abstract ports (LLM, retriever, outcome
sink) whose concrete adapters live at the edges. Tests inject fakes from
``takshashila_chatbot.testing``.
"""
