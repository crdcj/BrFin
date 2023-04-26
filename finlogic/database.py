"""Finlogic Database module.

This module provides functions to handle financial data from the CVM Portal. It
allows updating, processing and consolidating financial statements, as well as
searching for company names in the FinLogic Database and retrieving information
about the database itself.
"""

import os
from pathlib import Path
import pandas as pd
from . import config as cf
from . import cvm as cv


def get_finlogic_df() -> pd.DataFrame:
    """Returns the FinLogic Database as a Pandas DataFrame.

    Returns:
        A Pandas DataFrame containing the FinLogic Database.
    """
    # Start/load main dataframe
    if cf.FINLOGIC_DF_PATH.is_file():
        finlogic_df = pd.read_pickle(cf.FINLOGIC_DF_PATH)
    else:
        finlogic_df = pd.DataFrame()
    return finlogic_df


def consolidate_finlogic_df(filepaths: list):
    # Guard clause: if no raw file was update, there is nothing to consolidate
    if not filepaths:
        return
    # Concatenate all processed files into a single dataframe
    finlogic_df = pd.concat(
        [pd.read_pickle(filepath) for filepath in filepaths],
        ignore_index=True,
    )
    # Most values in datetime and string columns are the same.
    # So these remaining columns can be converted to category.
    columns = finlogic_df.select_dtypes(include=["datetime64[ns]", "object"]).columns
    finlogic_df[columns] = finlogic_df[columns].astype("category")
    # Keep only the newest 'report_version' in df if values are repeated
    cols = [
        "co_id",
        "report_type",
        "period_reference",
        "report_version",
        "period_order",
        "acc_method",
        "acc_code",
    ]
    finlogic_df.sort_values(by=cols, ignore_index=True, inplace=True)
    cols = finlogic_df.columns.tolist()
    cols_remove = ["report_version", "acc_value", "acc_fixed"]
    [cols.remove(col) for col in cols_remove]
    # Ascending order --> last is the newest report_version
    finlogic_df.drop_duplicates(cols, keep="last", inplace=True)
    finlogic_df.to_pickle(cf.FINLOGIC_DF_PATH)


def update_database(asynchronous: bool = False, cpu_usage: float = 0.75):
    """Verify changes in remote files and update them in Finlogic Database.

    Args:
        asynchronous: Generate the database by processing raw files
            asynchronously. Works only on Linux and Mac. Default is False.
        cpu_usage: A number between 0 and 1, where 1 represents 100% CPU usage.
            This argument will define the number of cpu cores used for data
            processing when function asynchronous mode is set to 'True'. Default
            is 0.75.

    Returns:
        None
    """
    # Create data folders if they do not exist.
    Path.mkdir(cf.RAW_DIR, parents=True, exist_ok=True)
    Path.mkdir(cf.PROCESSED_DIR, parents=True, exist_ok=True)

    # Define the number of cpu cores for parallel data processing.
    workers = int(os.cpu_count() * cpu_usage)
    if workers < 1:
        workers = 1
    print("Updating CVM files...")
    urls = cv.list_urls()
    # urls = urls[:1]  # Test
    updated_raw_filepaths = cv.update_cvm_files(urls)
    print(f"Number of CVM files updated = {len(updated_raw_filepaths)}")
    if updated_raw_filepaths:
        print("Updated files:")
        for updated_filepath in updated_raw_filepaths:
            print(f"    {cf.CHECKMARK} {updated_filepath.name} updated.")
    else:
        print("All files are up to date.")

    # Get updated years
    years_updated = [
        filepath.name.split("_")[3].split(".")[0] for filepath in updated_raw_filepaths
    ]
    years_updated.sort()
    years_updated = set(years_updated)

    # Get existing years in raw folder
    raw_filenames = [filepath.name for filepath in cf.RAW_DIR.glob("*.zip")]
    years_in_raw_folder = [
        filename.split("_")[3].split(".")[0] for filename in raw_filenames
    ]
    years_in_raw_folder.sort()
    years_in_raw_folder = set(years_in_raw_folder)

    # Get exisiting years in finlogic_df
    years_in_db = (
        pd.read_pickle(cf.FINLOGIC_DF_PATH)["period_reference"]
        .dt.year.unique()
        .tolist()
    )

    print("\nProcessing those files...")
    processed_filepaths = cv.process_annual_files(
        workers, updated_raw_filepaths, asynchronous=asynchronous
    )
    for processed_filepath in processed_filepaths:
        print(f"    {cf.CHECKMARK} {processed_filepath.stem} processed.")

    # Get the years in processed folder
    processed_filenames = [filepath.name for filepath in cf.PROCESSED_DIR.glob("*zst")]
    processed_years = file_years = [
        filename.split("_")[3].split(".")[0] for filename in filenames
    ]

    print("\nConsolidating processed files...")
    consolidate_finlogic_df(processed_filepaths)
    print('Updating "language" database...')
    process_language_df()
    print(f"{cf.CHECKMARK} FinLogic database updated!")


def database_info() -> dict:
    """Returns general information about FinLogic Database.

    This function generates a dictionary containing main information about
    FinLogic Database, such as the database path, file size, last update call,
    last modified dates, size in memory, number of accounting rows, unique
    accounting codes, companies, unique financial statements, first financial
    statement date and last financial statement date.

    Returns:
        A dictionary containing the FinLogic Database information.
    """
    finlogic_df = get_finlogic_df()
    if finlogic_df.empty:
        print("Finlogic Database is empty")
        return

    cvm_df = cv.get_cvm_df()
    file_date_unix = round(cf.FINLOGIC_DF_PATH.stat().st_mtime, 0)
    memory_size = finlogic_df.memory_usage(index=True, deep=True).sum()
    statements_cols = ["co_id", "report_version", "report_type", "period_reference"]
    statements_num = len(finlogic_df.drop_duplicates(subset=statements_cols).index)
    first_statement = finlogic_df["period_end"].astype("datetime64[ns]").min()
    last_statement = finlogic_df["period_end"].astype("datetime64[ns]").max()

    info_dict = {
        "Path": cf.DATA_PATH,
        "File size (MB)": round(cf.FINLOGIC_DF_PATH.stat().st_size / 1024**2, 1),
        "Last update call": cvm_df.index.max().round("1s").isoformat(),
        "Last modified": pd.Timestamp.fromtimestamp(file_date_unix).isoformat(),
        "Last updated data": cvm_df["last_modified"].max().isoformat(),
        "Memory size (MB)": round(memory_size / 1024**2, 1),
        "Accounting rows": len(finlogic_df.index),
        "Unique accounting codes": finlogic_df["acc_code"].nunique(),
        "Number of companies": finlogic_df["co_id"].nunique(),
        "Unique financial statements": statements_num,
        "First financial statement": first_statement.strftime("%Y-%m-%d"),
        "Last financial statement": last_statement.strftime("%Y-%m-%d"),
    }

    return info_dict


def search_company(company_name: str) -> pd.DataFrame:
    """Search for a company name in FinLogic Database.

    This function searches the 'co_name' column in the FinLogic Database for
    company names that contain the provided expression. It returns a DataFrame
    containing the search results, with each row representing a unique company
    that matches the search criteria.

    Args:
        company_name (str): A string to search for in the FinLogic Database
            'co_name' column.

    Returns:
        pd.DataFrame: A DataFrame containing the search results, with columns
            'co_name', 'co_id', and 'co_fiscal_id' for each unique company that
            matches the search criteria.
    """

    company_name = company_name.upper()
    df = (
        pd.read_pickle(cf.FINLOGIC_DF_PATH)
        .query("co_name.str.contains(@company_name)")
        .sort_values(by="co_name")
        .drop_duplicates(subset="co_id", ignore_index=True)[
            ["co_name", "co_id", "co_fiscal_id"]
        ]
    )
    return df


def process_language_df():
    """Process language dataframe."""
    language_df = pd.read_csv(cf.URL_LANGUAGE)
    Path.mkdir(cf.INTERIM_DIR, parents=True, exist_ok=True)
    language_df.to_csv(cf.LANGUAGE_DF_PATH, compression="zstd", index=False)
