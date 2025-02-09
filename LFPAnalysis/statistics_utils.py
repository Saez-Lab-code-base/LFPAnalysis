# In this libray I want to write some functions that make certain statistical analyses easier to run 

import numpy as np
import pandas as pd 
import statsmodels.formula.api as smf
from tqdm import tqdm
import patsy
from statsmodels.api import OLS
from tqdm import tqdm
import seaborn as sns
import matplotlib.pyplot as plt
from scipy import stats

import warnings 
warnings.filterwarnings('ignore')

def fit_permuted_model(y_permuted, X):
    """
    Convenience function for running backend OLS with surrogates
    """
    return OLS(y_permuted, X).fit().params

def permutation_regression_zscore(data, formula, n_permutations=1000, plot_res=False):
    """

    A quick way to perform single-electrode regression with many permutations: 
    # Example usage:
    # data = pd.DataFrame({'y': y, 'x1': x1, 'x2': x2, 'category': ['A', 'B', 'A', 'B', ...]})
    # formula = 'y ~ x1 + x2 + C(category)'
    # results = permutation_regression_zscore(data, formula, plot_res=True)
    # print(results)

    """
    # Perform original regression
    y, X = patsy.dmatrices(formula, data, return_type='dataframe')
    original_model = OLS(y, X).fit()
    
    # Extract original coefficients
    original_params = original_model.params
    
    # Prepare data for permutations
    y_values = y.values.ravel()
    X_values = X.values
    
    # Perform permutations
    permuted_params = []
    permuted_y_values = []
    for _ in tqdm(range(n_permutations), desc="Permutations"):
        y_permuted = np.random.permutation(y_values)
        permuted_params.append(fit_permuted_model(y_permuted, X_values))
        permuted_y_values.append(y_permuted)
    
    # Convert to numpy array for faster computations
    permuted_params = np.array(permuted_params)
    
    # Compute z-scores
    permuted_means = np.mean(permuted_params, axis=0)
    permuted_stds = np.std(permuted_params, axis=0)
    z_scores = (original_params - permuted_means) / permuted_stds
    
    # Compute p-values from z-scores
    p_values = 2 * (1 - stats.norm.cdf(np.abs(z_scores)))
    
    # Prepare results
    results = pd.DataFrame({
        'Original_Estimate': original_params,
        'Permuted_Mean': permuted_means,
        'Permuted_Std': permuted_stds,
        'Z_Score': z_scores,
        'P_Value': p_values
    })
    
    # Plotting
    if plot_res:
        features = [col for col in X.columns if col != 'Intercept']
        n_features = len(features)
        fig, axes = plt.subplots(n_features, 1, figsize=(3*n_features, 3*n_features), squeeze=False, dpi=300)
        
        for i, feature in enumerate(features):
            ax = axes[i, 0]
            
            # Plot permuted data first (in black)
            for j in range(min(100, n_permutations)):  # Limit to 100 permutations for clarity
                sns.regplot(x=X[feature], y=permuted_y_values[j], ax=ax, scatter=False,
                            line_kws={'color': 'black', 'alpha': 0.05}, ci=None)
            
            # Plot original data (in red)
            sns.regplot(x=X[feature], y=y_values, ax=ax, scatter_kws={'alpha': 0.5}, 
                        line_kws={'color': 'red', 'label': 'Original'}, ci=None)
            
            # Add z-score and p-value to the plot
            orig_param = original_params[i+1]
            z_score = z_scores[i+1]
            p_value = p_values[i+1]
            ax.text(0.05, 0.95, f'Beta: {orig_param:.2f}\nZ-score: {z_score:.2f}\np-value: {p_value:.3f}', 
                    transform=ax.transAxes, verticalalignment='top', 
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            
            ax.set_title(f'{feature} vs y')
            ax.legend()
            
            # Despine the plot
            sns.despine(ax=ax)
        
        plt.tight_layout()
        plt.show()
    
    return results

def time_resolved_regression_single_channel(timeseries=None, regressors=None, 
                             win_len=100, slide_len=25,
                             standardize=True, smooth=False, permute=False, sr=500):
    """
    In this function, if you provide a 2D array of z-scored time-varying neural data and a sert of regressors, 
    this function will run a time-resolved generalized linear model with the provided regressor dataframe. 

    Typically, this timeseries will be HFA, and the default win_len and slide_len reflect this 

    timeseries: ndarray, trials x times 
    regressors: pandas df, index = trials, columns = regressors

    Parameters
    ----------
    timeseries : 2D ndarray, dimensions = trials x times
        Time-varying neural data.
    regressors : pandas.DataFrame, dimensions = trials x regressors
        Dataframe containing the regressors.
    win_len : int
        Length of the window for the time-resolved regression.
    slide_len : int
        Step size for the time-resolved regression.
    standardize : bool
        Whether to standardize the regressors. The default is True.
    standardize : bool
        Whether to bin the timeseries according to win_len and slide_len. The default is Fault.
    sr: int
        sampling rate to determine the proper timing of the resulting timeseries of coefficients
    """

    # Optional: standardize the regressors
    if standardize:
        regressors = regressors.apply(lambda x: (x - np.nanmean(x))/(2*np.nanstd(x)))

    # Optional: bin the data
    if smooth: 
        slices = np.lib.stride_tricks.sliding_window_view(np.arange(timeseries.shape[-1]), win_len)[::slide_len]
        midpoints = np.ceil(np.mean(slices, axis=1))
        # Smooth the timeseries (easier to do here than to store smoothed data)
        sig = np.zeros([timeseries.shape[0], slices.shape[0]])
        for stride in range(slices.shape[0]):
            sig[:, stride] = np.nanmean(timeseries[:, slices[stride]], axis=1)
            # [np.nanmean(timeseries[trial, i:i+win_len]) for i in range(0, timeseries.shape[1], slide_len) if i+win_len <= timeseries.shape[1]]
    else:
        sig = timeseries

    all_res = []
    # write the regression formula
    formula = f'sig ~ 1+'+'+'.join(regressors.keys())
    for ts in range(sig.shape[-1]):
        regressors['sig'] = sig[:, ts]
        if permute:
            results = permutation_regression_zscore(regressors,
            formula,
            n_permutations=500, 
            plot_res=False)
            results['ts'] = ts
        else:
            y, X = patsy.dmatrices(formula, regressors, return_type='dataframe')
            original_model = OLS(y, X).fit()
            # Prepare results
            results = pd.DataFrame({
                'Original_Estimate': original_model.params,
                'Original_BSE': original_model.bse,
                'P_Value': original_model.pvalues,
                'ts': ts 
            })
        all_res.append(results)
        
    all_res = pd.concat(all_res)

    if smooth: # assign the timestamp to the middle of each bin in samples
        for ts_i in all_res.ts.unique():
            all_res.loc[all_res.ts==ts_i, 'ts'] = midpoints[ts_i] * (1000/sr)
    else:
        all_res['ts'] = all_res['ts'] * (1000/sr)

    return all_res

def mixed_effects_electrodes(model_df, predictor, re_var='participant', plot=True):
    """
    This function is for instances in which you've computed an electrode-level measure
    and you want to know if this measure is significant in a region. 
    
    Your first inclination might be to do a t-test of the population of all electrodes in the region against 0. 
    
    However, different patients contribute different numbers of electrodes, 
    and an effect might be driven by just the electrodes in one patient! 
    
    So, we want to do a mixed-effects regression with subject as a random effect to assess
    whether this region effect, grouped across electrodes, is consistent across patients
    
    Parameters
    ----------
    model_df : pd.DataFrame
        A dataframe with columns for the predictor variable and the random effect variable
    predictor : str
        The name of the column in model_df that contains the predictor variable
    re_var : str
        The name of the column in model_df that contains the random effect variable
    plot : bool
        Whether to plot the results

    Returns
    -------
    results : statsmodels.regression.mixed_linear_model.MixedLMResults
        The results of the mixed-effects regression
    
    
    """
    
    model = smf.mixedlm(f"{predictor} ~ 1", data=model_df, groups=f'{re_var}')
    results = model.fit()
    
    if plot:
        # Create a scatter plot of individual data points
        fig, ax = plt.subplots(1, 1, figsize=(10, 5), dpi=300)
        sns.stripplot(x=f'{re_var}', y=f'{predictor}', data=model_df, 
                      jitter=True, alpha=0.6, color="gray", s=6, ax=ax)

        # plot the mean line
        subject_means = model_df.groupby(f'{re_var}')[f'{predictor}'].mean()

        sns.boxplot(showmeans=True,
                    meanline=True,
                    meanprops={'color': 'k', 'ls': '-', 'lw': 2},
                    medianprops={'visible': False},
                    whiskerprops={'visible': False},
                    zorder=10,
                    x=subject_means.index,
                    y=subject_means.values,
                    showfliers=False,
                    showbox=False,
                    showcaps=False,
                    ax=ax)

        # # Overlay the subject means

        # Plot the overall mean from the mixed-effects model
        overall_mean = results.fe_params['Intercept']
        ci = results.conf_int().loc['Intercept']
        
        plt.axhline(overall_mean, color="blue", linestyle="--", label=f"Overall Mean: {overall_mean:.2f}")
        plt.axhline(ci[0], color='red', linestyle='--')
        plt.axhline(ci[1], color='red', linestyle='--')

        plt.axhline(0, color='black')
        sns.despine()
        
    return results
    
############################################################################################################

# In Progress: 

# TODO: Write a generalized class for time-resolved analyses that can be used for any input function like 
# fit_permuted_model seen above. 

# class TimeResolvedAnalysis:
#     # This class is meant to be a general class for time-resolved analyses. 
#     # It should take any function that can be applied to a single timeseries and 
#     # perform this function over some sliding window.
#     def __init__(self, data, function, win_len=100, slide_len=25):
#         self.data = data
#         self.win_len = win_len
#         self.slide_len = slide_len
#         self.results = None

#     def function(self, data):
#         """
#         This function should take a single timeseries and return a result. 
#         """
#         pass

#     def run(self):
#         """
#         This function will run the time-resolved analysis over the data provided in the class
#         """
#         slices = np.lib.stride_tricks.sliding_window_view(np.arange(self.data.shape[-1]), self.win_len)[::self.slide_len]
#         midpoints = np.ceil(np.mean(slices, axis=1))
#         results = []
#         for ts in range(slices.shape[-1]):
#             results.append(self.function(self.data[:, slices[ts]]))
#         self.results = pd.DataFrame(results)
#         self.results['ts'] = midpoints
#         return self.results
    
#     def plot(self):
#         """
#         This function will plot the results of the time-resolved analysis
#         """
#         if self.results is None:
#             self.run()
#         features = [col for col in self.results.columns if col != 'ts']
#         n_features = len(features)
#         fig, axes = plt.subplots(n_features, 1, figsize=(3*n_features, 3*n_features), squeeze=False, dpi=300)

#         for i, feature in enumerate(features):
#             ax = axes[i, 0]

#             # Plot original data (in red)
#             sns.lineplot(x=self.results['ts'], y=self.results[feature], ax=ax, color='red', label='Original')

#             ax.set_title(f'{feature} vs ts')
#             ax.legend()

#             # Despine the plot
#             sns.despine(ax=ax)

#         plt.tight_layout()
#         plt.show()

# class TimeResolvedRegression(TimeResolvedAnalysis):
#     def __init__(self, data, regressors, win_len=100, slide_len=25, standardize=True):
#         super().__init__(data, win_len, slide_len)
#         self.regressors = regressors
#         self.standardize = standardize

#     def function(self, data):
#         y, X = patsy.dmatrices(formula, regressors, return_type='dataframe')
#         model = OLS(y, X).fit()
#         return model.params