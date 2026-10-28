import os

import pandas as pd
from agent_framework import Executor, WorkflowContext, handler

from src.bussiness.ingestion.filter import filter_files
from src.core.logger import logger
from src.models.ingestion import Files, SheetData, SpreadsheetData


class SpreadsheetExecutor(Executor):
    @handler
    async def extract_spreadsheet(
        self,
        files: Files,
        ctx: WorkflowContext[SpreadsheetData],
    ):

        logger.info("Spreadsheet executor initiated")

        spreadsheet_files = filter_files(files, [".xlsx", ".csv"])

        if not spreadsheet_files:
            logger.info("No spreadsheet files found")

            return

        logger.info(f"Spreadsheet files to extract: {len(spreadsheet_files)}")

        for file in spreadsheet_files:
            try:
                file_path = file.file_path

                sheets = []

                if file.extension == ".csv":
                    df = pd.read_csv(file_path)

                    sheet = SheetData(
                        sheet_name="data",
                        columns=[str(column) for column in df.columns],
                        rows=df.to_dict(orient="records"),
                        metadata={
                            "rows": len(df),
                            "columns": len(df.columns),
                        },
                    )

                    sheets.append(sheet)

                elif file.extension == ".xlsx":
                    excel_sheets = pd.read_excel(file_path, sheet_name=None)

                    for sheet_name, df in excel_sheets.items():
                        sheet = SheetData(
                            sheet_name=str(sheet_name),
                            columns=[str(column) for column in df.columns],
                            rows=df.to_dict(orient="records"),
                            metadata={
                                "rows": len(df),
                                "columns": len(df.columns),
                            },
                        )

                        sheets.append(sheet)

                spreadsheet_data = SpreadsheetData(
                    file_name=os.path.basename(file_path),
                    file_type=file.extension,
                    sheets=sheets,
                    metadata={
                        "file_path": str(file_path),
                        "number_of_sheets": len(sheets),
                    },
                )

                await ctx.send_message(spreadsheet_data)

                logger.info(f"Spreadsheet extraction completed: {file_path}")

            except Exception as e:  # noqa: BLE001 - Isolate extraction failures per file.
                logger.exception(
                    f"Error in spreadsheet executor: {file.file_path} - {e}"
                )

        logger.info("Spreadsheet executor completed")
