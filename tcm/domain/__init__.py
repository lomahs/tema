"""Domain models and the vocabularies that classify them.

Nothing here touches Flask, pandas, openpyxl, requests or msal. The four vocabulary
singletons read their JSON at import through `tcm.settings`, which is the one
place outside the layers.
"""
