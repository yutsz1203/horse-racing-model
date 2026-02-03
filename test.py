import pandas as pd
import pymupdf  # imports the pymupdf library

doc = pymupdf.open("source/2025-StandardTimes-SectionalTimes.pdf")  # open a document
for page in doc:  # iterate the document pages
    tables = page.find_tables()  # get plain text encoded as UTF-8
    for table in tables:
        df = table.to_pandas()
        print(df)
