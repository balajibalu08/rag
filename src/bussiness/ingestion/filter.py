from src.models.ingestion import Files


def filter_files(
    files: Files,
    extensions: list[str],
):
    filtered_files = []

    for file in files.files:
        if file.extension and file.extension.lower() in extensions:
            filtered_files.append(file)

    return filtered_files
