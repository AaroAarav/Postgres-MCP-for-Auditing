def format_results(records: list[dict], empty_msg: str = "No data found.") -> str:
    """Helper to convert a list of dictionaries into a Markdown table for the LLM."""
    if not records:
        return empty_msg
    
    headers = list(records[0].keys())
    header_row = "| " + " | ".join(str(h) for h in headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    rows = []
    for record in records:
        row_str = "| " + " | ".join(str(record.get(h, "")).replace("\n", " ").replace("\r", "") for h in headers) + " |"
        rows.append(row_str)
        
    return "\n".join([header_row, separator] + rows)