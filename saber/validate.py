import logging
import os
import warnings
from multiprocessing import Pool

import hydrostats as hs
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from sklearn.model_selection import RepeatedKFold as RKFolds

from .assign import map_assign_ungauged
from .assign import mp_assign_all
from .calibrate import map_saber, mp_saber
from .io import asgn_gid_col
from .io import asgn_mid_col
from .io import dir_valid
from .io import gid_col
from .io import mid_col
from .io import q_mod
from .io import q_obs
from .io import q_sim

__all__ = ['kfolds', 'bootstrap', 'mp_bootstrap', 'bootstrap_figures']

logger = logging.getLogger(__name__)

warnings.filterwarnings('ignore')


def kfolds(workdir: str, assign_df: pd.DataFrame, gauge_data: str, hds: str,
           n_splits: int = 5, n_repeats: int = 10, n_processes: int or None = None) -> None:
    """
    Performs a k-fold validation of the calibration results. The validation set is randomly selected from the
    gauges table. The validation set is then removed from the calibration set and the calibration is repeated
    n_repeats times. The validation set is then added back to the calibration set and the calibration is repeated
    n_repeats times. This process is repeated n_folds times.

    Args:
        workdir: the project working directory
        assign_df: a completed assignment dataframe already filled by a successful SABER assignment run
        gauge_data: path to the directory of observed data
        hds: string path to the hindcast streamflow dataset
        n_splits: the number of folds to create in each iteration
        n_repeats: the number of repeats to perform
        n_processes: number of processes to use for multiprocessing, passed to Pool

    Returns:
        pandas.DataFrame
    """
    # subset the assign dataframe to only rows which contain gauges & reset the index
    assign_df = assign_df[assign_df[gid_col].notna()].reset_index(drop=True)

    for i, (train_rows, test_rows) in enumerate(RKFolds(n_splits=n_splits, n_repeats=n_repeats).split(assign_df.index)):
        # make a copy of the dataframe to work with for this iteration
        val_df = assign_df.copy()

        # on the test rows, clear the gid column so that it is not assigned to the gauge it contains
        val_df.loc[test_rows, gid_col] = np.nan

        # make assignments on the training set
        val_df = mp_assign_all(workdir, val_df, n_processes=n_processes)

        # reduce the dataframe to only the test rows (index/row-order gets shuffled by mp assigning)
        val_df = val_df[val_df[gid_col].isna()].reset_index(drop=True)

        # bias correct only at the gauges in the test set
        mp_saber(val_df, hds, gauge_data, os.path.join(workdir, dir_valid), n_processes=n_processes)

        # todo calculate metrics for the test set
    return


def bootstrap(row_idx: int, assign_df: pd.DataFrame, gauge_data: str, hds: str,
              save_dir: str) -> pd.DataFrame | None:
    """
    Performs bootstrap validation.

    Args:
        row_idx: the row of the assignment table to remove and perform bootstrap validation with
        assign_df: pandas.DataFrame of the assignment table
        gauge_data: string path to the directory of observed data
        hds: string path to the hindcast streamflow dataset
        save_dir: string path to the directory to save the corrected data

    Returns:
        None
    """
    try:
        row = assign_df.loc[row_idx]
        assigned_row = map_assign_ungauged(assign_df, assign_df.drop(row_idx), row[mid_col])
        corrected_df = map_saber(
            assigned_row[mid_col].values[0],
            assigned_row[asgn_mid_col].values[0],
            assigned_row[asgn_gid_col].values[0],
            hds,
            gauge_data,
            save_dir
        )

        if corrected_df is None:
            logger.warning(f'No corrected data for {row[mid_col]}')
            return None
        if not all([q_mod in corrected_df.columns, q_sim in corrected_df]):
            logger.warning(f'missing columns')
            return None

        metrics_df = pd.read_csv(os.path.join(gauge_data, f'{row[gid_col]}.csv'), index_col=0)
        metrics_df.columns = [q_obs, ]
        metrics_df.index = pd.to_datetime(metrics_df.index)
        metrics_df = pd.merge(corrected_df, metrics_df, how='inner', left_index=True, right_index=True)

        obs_values = metrics_df[q_obs].values.flatten()
        sim_values = metrics_df[q_sim].values.flatten()
        mod_values = np.squeeze(metrics_df[q_mod].values.flatten())

        if mod_values.dtype == np.dtype('O'):
            mod_values = np.array(mod_values.tolist()).astype(np.float64).flatten()

        diff_sim = sim_values - obs_values
        diff_corr = mod_values - obs_values

        return pd.DataFrame({
            'me_sim': np.mean(diff_sim),
            'mae_sim': np.mean(np.abs(diff_sim)),
            'rmse_sim': np.sqrt(np.mean(diff_sim ** 2)),
            'nse_sim': hs.nse(sim_values, obs_values),
            'kge_sim': hs.kge_2012(sim_values, obs_values),

            'me_corr': np.mean(diff_corr),
            'mae_corr': np.mean(np.abs(diff_corr)),
            'rmse_corr': np.sqrt(np.mean(diff_corr ** 2)),
            'nse_corr': hs.nse(mod_values, obs_values),
            'kge_corr': hs.kge_2012(mod_values, sim_values),

            'reach_id': row[mid_col],
            'gauge_id': row[gid_col],
            'asgn_reach_id': assigned_row[asgn_mid_col],
        })
    except Exception as e:
        logger.error(e)
        logger.error(f'Failed bootstrap validation for {row[mid_col]}')
        return None


def mp_bootstrap(workdir: str, assign_df: pd.DataFrame, gauge_data: str, hds: str, n_processes: int = 1) -> None:
    """
    Performs bootstrap validation using multiprocessing.

    Args:
        workdir: the project working directory
        assign_df: pandas.DataFrame of the assignment table
        gauge_data: string path to the directory of observed data
        hds: string path to the hindcast streamflow dataset
        n_processes: number of processes to use for multiprocessing, passed to Pool

    Returns:
        None
    """
    # subset the assign dataframe to only rows which contain gauges & reset the index
    assign_df = assign_df[assign_df[gid_col].notna()].reset_index(drop=True)
    save_dir = os.path.join(workdir, dir_valid)

    with Pool(n_processes) as p:
        metrics_df = pd.concat(
            p.starmap(
                bootstrap,
                [[idx, assign_df, gauge_data, hds, save_dir] for idx in assign_df.index]
            )
        )

    metrics_df.to_csv(os.path.join(save_dir, 'bootstrap_metrics.csv'), index=False)

    return


def bootstrap_figures(workdir: str, df: pd.DataFrame = None, stat: str = None) -> None:
    """

    Args:
        workdir: the project working directory
        df: pandas.DataFrame of the bootstrap metrics
        stat: the statistic to plot

    Returns:
        None
    """
    if df is None:
        df = pd.read_csv(os.path.join(workdir, dir_valid, 'bootstrap_metrics.csv'), index_col=0)

    if stat is None:
        for stat in ['me', 'mae', 'rmse', 'nse', 'kge']:
            bootstrap_figures(workdir, df, stat)
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4), dpi=1500, tight_layout=True, sharey=True)

    if stat == 'kge':
        binwidth = 0.5
        binrange = (-6, 1)
        ax1.axvline(-0.44, c='red', linestyle='--')
        ax2.axvline(-0.44, c='red', linestyle='--')

    elif stat == 'nse':
        binwidth = 0.5
        binrange = (-6, 1)

    elif stat == 'me':
        binwidth = 20
        binrange = (-200, 200)

    elif stat == 'mae':
        binwidth = 30
        binrange = (0, 300)

    elif stat == 'rmse':
        binwidth = 20
        binrange = (0, 200)

    else:
        raise ValueError(f'Invalid statistic: {stat}')

    fig.suptitle(f'Bootstrap Validation: {stat.upper()}')
    ax1.grid(True, 'both', zorder=0, linestyle='--')
    ax2.grid(True, 'both', zorder=0, linestyle='--')
    ax1.set_xlim(binrange)
    ax2.set_xlim(binrange)

    stat_df = df[[f'{stat}_corr', f'{stat}_sim']].reset_index(drop=True).copy()
    stat_df[stat_df <= binrange[0]] = binrange[0]
    stat_df[stat_df >= binrange[1]] = binrange[1]

    sns.histplot(stat_df, x=f'{stat}_sim', binwidth=binwidth, binrange=binrange, ax=ax1)
    sns.histplot(stat_df, x=f'{stat}_corr', binwidth=binwidth, binrange=binrange, ax=ax2)

    ax1.axvline(stat_df[f'{stat}_sim'].median(), c='green')
    ax2.axvline(stat_df[f'{stat}_corr'].median(), c='green')

    fig.savefig(os.path.join(workdir, dir_valid, f'bootstrap_{stat}.png'))
    return
