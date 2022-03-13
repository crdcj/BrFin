"""Module containing Financial Class definition for company financials.
Abbreviation used for Financial Statement = FS
"""
import os
import numpy as np
import pandas as pd


class Finance():
    """Company Financials Class for Brazilian Companies."""

    script_dir = os.path.dirname(__file__)
    DATASET = pd.read_pickle(script_dir + '/data/processed/dataset.pkl.zst')
    TAX_RATE = 0.34
    CVM_IDS = list(DATASET['cvm_id'].unique())
    FISCAL_IDS = list(DATASET['fiscal_id'].unique())

    def __init__(
        self,
        corporation_id,
        account_basis: str = 'consolidated',
        first_period: str = '2009-12-31',
        last_period: str = '2200-12-31',
        show_accounts: int = 0,
        unit: float = 1
    ):
        """Initialize main variables.

        Args:
            corporation_id: can be used both CVM (regulator) ID  or Fiscal ID.
                CVM ID must be an integer
                Fiscal ID must be a string in the format: 'XX.XXX.XXX/XXXX-XX'
            account_basis (str, optional): 'consolidated' or 'separate'.
            first_period: first accounting period in YYYY-MM-DD format
            last_period: last accounting period in YYYY-MM-DD format
            unit (float, optional): number to divide account values
            show_accounts: account levels to show (default = show all accounts)
        """
        self.corporation_id = corporation_id
        self.account_basis = account_basis
        self.first_period = first_period
        self.last_period = last_period
        self.unit = unit
        self.show_accounts = show_accounts
        self._set_main_df()

    @classmethod
    def search_company(cls, expression: str) -> pd.DataFrame:
        """Return dataframe with companies that matches the 'expression'"""
        expression = expression.upper()
        mask = cls.DATASET.company_name.str.contains(expression)
        df = cls.DATASET[mask].copy()
        df.sort_values(by='company_name', inplace=True)
        df.drop_duplicates(subset='cvm_id', inplace=True, ignore_index=True)
        columns = ['company_name', 'cvm_id', 'fiscal_id']
        return df[columns]

    @property
    def corporation_id(self):
        """Return company selected identifier if it exists in DATASET."""
        return self._corporation_id

    @corporation_id.setter
    def corporation_id(self, value):
        self._corporation_id = value
        if value in Finance.CVM_IDS:
            self._cvm_id = value
            df = Finance.DATASET.query('cvm_id == @self._cvm_id').copy()
            df.reset_index(drop=True, inplace=True)
            self._fiscal_id = df.loc[0, 'fiscal_id']
        elif value in Finance.FISCAL_IDS:
            self._fiscal_id = value
            df = Finance.DATASET.query('fiscal_id == @self._fiscal_id').copy()
            df.reset_index(drop=True, inplace=True)
            self._cvm_id = df.loc[0, 'cvm_id']
        else:
            raise ValueError(
                "Selected CVM ID or Fiscal ID for the Company  not found")

    @property
    def account_basis(self):
        """Return selected FS type (account_basis).

        Options are: 'consolidated' or 'separate'
        """
        return self._report_type

    @account_basis.setter
    def account_basis(self, value):
        if value in ('consolidated', 'separate'):
            self._report_type = value
        else:
            raise ValueError("Select 'consolidated' or 'separate' report type")

    @property
    def first_period(self):
        """Return selected start date for filtering FS end period."""
        return self._min_end_period

    @first_period.setter
    def first_period(self, value):
        value = pd.to_datetime(value, errors='coerce')
        if value == pd.NaT:
            print('Inserted first_period period not in YYYY-MM-DD format')
            print('2009-12-31 selected instead')
            self._min_end_period = pd.to_datetime('2009-12-31')
        else:
            self._min_end_period = value

    @property
    def last_period(self):
        """Return selected end date for filtering FS end period."""
        return self._max_end_period

    @last_period.setter
    def last_period(self, value):
        value = pd.to_datetime(value, errors='coerce')
        if value == pd.NaT:
            print('Inserted last_period not in YYYY-MM-DD format')
            print('2200-12-31 selected instead')
            self._max_end_period = pd.to_datetime('2200-12-31')
        else:
            self._max_end_period = value

    @property
    def show_accounts(self):
        """Return account levels to show: default = 0 (show all accounts).
        X.YY.ZZ.WW...   level 0
        X.YY            level 1
        X.YY.ZZ         level 2
        X.YY.ZZ.YY      level 3
        """

        return self._account_mode

    @show_accounts.setter
    def show_accounts(self, value):
        if value in [0, 1, 2, 3]:
            self._account_mode = value
        else:
            raise ValueError(
                "Account levels are: 0 (show all accounts), 1, 2, 3.")

    @property
    def unit(self):
        """Return the number by which account values are being divided."""
        return self._unit

    @unit.setter
    def unit(self, value):
        if value > 0:
            self._unit = value
        else:
            raise ValueError("Unit value must be greater than 0")

    def _set_main_df(self) -> pd.DataFrame:
        self._MAIN_DF = Finance.DATASET.query('cvm_id == @self._cvm_id').copy()
        self._MAIN_DF = self._MAIN_DF.astype({
            'cvm_id': np.uint32,
            'fiscal_id': str,
            'company_name': str,
            'report_type': str,
            'report_version': str,
            'period_reference': 'datetime64',
            'period_begin': 'datetime64',
            'period_end': 'datetime64',
            'period_order': np.int8,
            'account_code': str,
            'account_name': str,
            'account_basis': str,
            'account_fixed': bool,
            'account_value': float,
            'equity_statement_column': str,
        })
        """
        df['account_code'].str[0].unique() -> [1, 2, 3, 4, 5, 6, 7]
        The first part of 'account_code' is the FS type
        Table of statements correspondence:
            1 -> Balance Sheet - Assets
            2 -> Balance Sheet - Liabilities and Shareholders’ Equity
            3 -> Income
            4 -> Comprehensive Income
            5 -> Changes in Equity
            6 -> Cash Flow (Indirect Method)
            7 -> Added Value
        """
        self._MAIN_DF.sort_values(
            by='account_code',
            ignore_index=True,
            inplace=True
        )

    def _get_company_df(self) -> pd.DataFrame:
        expression = '''
            account_basis == @self.account_basis and \
            period_end >= @self.first_period and \
            period_end <= @self.last_period
        '''
        df = self._MAIN_DF.query(expression).copy()
        # change unit only for accounts different from 3.99
        df['account_value'] = np.where(
            df['account_code'].str.startswith('3.99'),
            df['account_value'],
            df['account_value'] / self._unit
        )
        # show only selected accounting levels
        df['account_code_len'] = df['account_code'].str.len()
        if self.show_accounts > 0:
            account_code_limit = self.show_accounts * 3 + 1  # noqa
            df.query('account_code_len <= @account_code_limit', inplace=True)
        df.reset_index(drop=True, inplace=True)

        return df

    @property
    def info(self) -> dict:
        """Return company info."""
        dfa = self._MAIN_DF.query('report_type == "annual"')
        dfq = self._MAIN_DF.query('report_type == "quarterly"')
        fmt = '%Y-%m-%d'
        first_annual_report = dfa['period_reference'].min().strftime(fmt)
        last_annual_report = dfa['period_reference'].max().strftime(fmt)
        last_quarterly_report = dfq['period_reference'].max().strftime(fmt)

        company_info = {
            'CVM Number': self._MAIN_DF.loc[0, 'cvm_id'],
            'Fiscal Number': self._MAIN_DF.loc[0, 'fiscal_id'],
            'Company Name': self._MAIN_DF.loc[0, 'company_name'],
            'First Annual Report': first_annual_report,
            'Last Annual Report': last_annual_report,
            'Last Quarterly Report': last_quarterly_report,
        }
        return company_info

    @property
    def assets(self) -> pd.DataFrame:
        """Return company assets."""
        df = self._get_company_df()
        df.query('account_code.str.startswith("1")', inplace=True)
        return self._make_report(df)

    @property
    def liabilities_and_equity(self) -> pd.DataFrame:
        """Return company liabilities and equity."""
        df = self._get_company_df()
        df.query('account_code.str.startswith("2")', inplace=True)
        return self._make_report(df)

    @property
    def liabilities(self) -> pd.DataFrame:
        """Return company liabilities."""
        df = self._get_company_df()
        expression = '''
            account_code.str.startswith("2.01") or \
            account_code.str.startswith("2.02")',
        '''
        df.query(expression, inplace=True)
        return self._make_report(df)

    @property
    def equity(self) -> pd.DataFrame:
        """Return company equity."""
        df = self._get_company_df()
        df.query('account_code.str.startswith("2.03")', inplace=True)
        return self._make_report(df)

    @property
    def earnings_per_share(self) -> pd.DataFrame:
        """Return company equity.
        3.99                -> Earnings per Share (BRL / Share)
            3.99.01         -> Earnings per Share
                3.99.01.01  -> ON (ordinary)
            3.99.02         -> Diluted Earnings per Share
                3.99.02.01  -> ON (ordinary)
        """
        df = self._get_company_df()
        df.query(
            'account_code == "3.99.01.01" or account_code == "3.99.02.01"',
            inplace=True
        )

        return self._make_report(df)

    @staticmethod
    def calculate_ltm(df_flow: pd.DataFrame) -> pd.DataFrame:
        last_annual = df_flow.query(
            'report_type == "annual"')['period_end'].max()
        last_quarterly = df_flow.query(
            'report_type == "quarterly"')['period_end'].max()
        if last_annual > last_quarterly:
            df_flow.query('report_type == "annual"', inplace=True)
            return df_flow

        df1 = df_flow.query('period_end == @last_quarterly').copy()
        df1.query('period_begin == period_begin.min()', inplace=True)

        df2 = df_flow.query('period_reference == @last_quarterly').copy()
        df2.query('period_begin == period_begin.min()', inplace=True)
        df2['account_value'] = -df2['account_value']

        df3 = df_flow.query('period_end == @last_annual').copy()

        df_ltm = pd.concat([df1, df2, df3], ignore_index=True)
        df_ltm = df_ltm[['account_code', 'account_value']]
        df_ltm = df_ltm.groupby(by='account_code').sum().reset_index()
        df1.drop(columns='account_value', inplace=True)
        df_ltm = pd.merge(df1, df_ltm)
        df_ltm['report_type'] = 'ltm'
        df_ltm['period_begin'] = last_quarterly - pd.DateOffset(years=1)

        df_flow.query('report_type == "annual"', inplace=True)
        df_flow_ltm = pd.concat([df_flow, df_ltm], ignore_index=True)
        return df_flow_ltm

    @property
    def income(self) -> pd.DataFrame:
        """Return company income statement."""
        df = self._get_company_df()
        df.query('account_code.str.startswith("3")', inplace=True)
        df = Finance.calculate_ltm(df)
        return self._make_report(df)

    @property
    def cash_flow(self) -> pd.DataFrame:
        """Return company income statement."""
        df = self._get_company_df()
        df.query('account_code.str.startswith("6")', inplace=True)
        df = Finance.calculate_ltm(df)
        return self._make_report(df)

    @staticmethod
    def account_value(account_code: str, df: pd.DataFrame) -> float:
        """Return value for an account in dataframe."""
        df.query('account_code == @account_code', inplace=True)
        return df.iloc[0]['account_value']

    @staticmethod
    def shift_right(s: pd.Series, is_on: bool) -> pd.Series:
        """Shift row to the right in order to obtain series previous values"""
        if is_on:
            arr = s.iloc[:-1].values
            return np.append(np.nan, arr)
        else:
            return s

    def operating_performance(self, is_on: bool = True):
        """Return company main operating indicators."""
        df = self._get_company_df()
        df_as = self.assets
        # df_as.query('account_code == "1"', inplace=True)
        df_le = self.liabilities_and_equity
        # df_le.query('account_code == "2.03"', inplace=True)
        df_in = self.income
        # df_in.query('account_code == "3.11"', inplace=True)
        df = pd.concat([df_as, df_le, df_in], ignore_index=True)
        df.set_index(keys='account_code', drop=True, inplace=True)
        df.drop(columns=['account_fixed', 'account_name'], inplace=True)

        # series definition
        revenues = df.loc['3.01']
        gross_profit = df.loc['3.03']
        ebit = df.loc['3.05']
        net_income = df.loc['3.11']
        total_assets = self.shift_right(df.loc['1'], is_on)
        equity = self.shift_right(df.loc['2.03'], is_on)
        invested_capital = (
            df.loc['2.03']
            + df.loc['2.01.04']
            + df.loc['2.02.01']
            - df.loc['1.01.01']
            - df.loc['1.01.02']
        )
        invested_capital = self.shift_right(invested_capital, is_on)

        # indicators calculation
        df.loc['return_on_assets'] = (
            ebit * (1 - Finance.TAX_RATE) / total_assets
        )
        df.loc['return_on_capital'] = (
            ebit * (1 - Finance.TAX_RATE) / invested_capital
        )
        df.loc['return_on_equity'] = net_income / equity
        df.loc['gross_margin'] = gross_profit / revenues
        df.loc['operating_margin'] = ebit * (1 - Finance.TAX_RATE) / revenues
        df.loc['net_margin'] = net_income / revenues

        # discard rows used for calculation
        df = df.iloc[-6:]
        # discard index name 'account_code'
        df.index.name = None
        # df.reset_index(drop=True, inplace=True)
        return df

    def get_accounts(self, accounts: list) -> pd.DataFrame:
        df_as = self.assets
        df_le = self.liabilities_and_equity
        df_is = self.income
        df_cf = self.cash_flow
        df = pd.concat([df_as, df_le, df_is, df_cf], ignore_index=True)
        df.query('account_code == @accounts', inplace=True)
        return df

    def _make_report(self, df: pd.DataFrame) -> pd.DataFrame:
        # keep only last quarterly fs
        last_end_period = df.period_end.max()  # noqa
        expression = '''
            report_type == 'annual' or \
            period_end == @last_end_period
        '''
        df.query(expression, inplace=True)
        # sort for drop operation
        df.sort_values(
            ['period_end', 'period_reference', 'account_code'],
            inplace=True
        )
        # only last published statements will be used
        df['financial_year'] = df.period_end.dt.year
        df.drop_duplicates(
            subset=['financial_year', 'account_code'],
            keep='last',
            inplace=True,
            ignore_index=True
        )
        base_columns = ['account_name', 'account_code', 'account_fixed']
        df_report = df.loc[:, base_columns]
        df_report.drop_duplicates(ignore_index=True, inplace=True)

        merge_columns = base_columns + ['account_value']
        for period in df.period_end.unique():
            # print(date)
            df_year = df.query('period_end == @period').copy()
            df_year = df_year[merge_columns]
            period_str = np.datetime_as_string(period, unit='D')
            df_year.rename(columns={'account_value': period_str}, inplace=True)
            df_report = pd.merge(df_report, df_year, how='left')

        df_report.sort_values('account_code', ignore_index=True, inplace=True)
        return df_report
