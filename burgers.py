#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Mar 31 12:53:27 2023

@author: maslyaev
"""

import numpy as np

import torch
import os
from functools import reduce


import matplotlib.pyplot as plt
import matplotlib

SMALL_SIZE = 12
matplotlib.rc('font', size=SMALL_SIZE)
matplotlib.rc('axes', titlesize=SMALL_SIZE)

from scipy.io import loadmat

import pysindy as ps

from epde.interface.logger import Logger
from epde.interface.equation_translator import translate_equation
import epde.interface.interface as epde_alg
from epde.interface.prepared_tokens import TrigonometricTokens, CacheStoredTokens
from epde.interface.solver_integration import BOPElement, SolverAdapter

def translate_sindy_eq(equation: str):
    correspondence = {"0" : "u{power: 1.0}",
                      "0_1" : "du/dx2{power: 1.0}",
                      "0_11" : "d^2u/dx2^2{power: 1.0}",
                      "0_111" : "d^3u/dx2^3{power: 1.0}"}
    terms = []
    
    def replace(term):
        term = term.replace(' ', '').split('x')
        for idx, factor in enumerate(term[1:]):
            try:
                term[idx+1] = correspondence[factor]
            except KeyError:
                print(f'Key of term {factor} is missing')
                raise KeyError()
        return term
                
    for term in equation.split('+'):
        terms.append(reduce(lambda x, y: x + ' * ' + y, replace(term)))
    terms_comb = reduce(lambda x, y: x + ' + ' + y, terms) + ' + 0.0 = du/dx1{power: 1.0}'
    return terms_comb

def Heatmap(Matrix, interval = None, area = ((0, 1), (0, 1)), xlabel = '', ylabel = '', 
            figsize=(8,6), filename = None, title = '', filename_type = 'eps'):
    y, x = np.meshgrid(np.linspace(area[0][0], area[0][1], Matrix.shape[0]), np.linspace(area[1][0], area[1][1], Matrix.shape[1]))
    fig, ax = plt.subplots(figsize = figsize)
    plt.xlabel(xlabel)
    ax.set(ylabel=ylabel)
    ax.xaxis.labelpad = -10
    if interval:
        c = ax.pcolormesh(x, y, np.transpose(Matrix), cmap='RdBu', vmin=interval[0], vmax=interval[1])    
    else:
        c = ax.pcolormesh(x, y, np.transpose(Matrix), cmap='RdBu', vmin=min(-abs(np.max(Matrix)), -abs(np.min(Matrix))),
                          vmax=max(abs(np.max(Matrix)), abs(np.min(Matrix)))) 
    ax.axis([x.min(), x.max(), y.min(), y.max()])
    fig.colorbar(c, ax=ax)
    plt.title(title)
    if type(filename) != type(None): plt.savefig(filename + '.' + filename_type, format=filename_type)
    plt.show()

def get_epde_pool(x, t, u, use_ann = False):
    grids = np.meshgrid(t, x, indexing = 'ij')
    print(u.shape, grids[0].shape, grids[1].shape)
    multiobjective_mode = True
    dimensionality = u.ndim - 1
    
    epde_search_obj = epde_alg.EpdeSearch(multiobjective_mode=multiobjective_mode, use_solver = False, 
                                          dimensionality = dimensionality, boundary = 10,
                                          coordinate_tensors = grids)    
    
    if use_ann:
        epde_search_obj.set_preprocessor(default_preprocessor_type='ANN', # use_smoothing = True
                                          preprocessor_kwargs={'epochs_max' : 2})
    popsize = 7
    if multiobjective_mode:
        epde_search_obj.set_moeadd_params(population_size = popsize, 
                                          training_epochs=65)
    else:
        epde_search_obj.set_singleobjective_params(population_size = popsize, 
                                                   training_epochs=65)
    
    custom_grid_tokens = CacheStoredTokens(token_type = 'grid',
                                           token_labels = ['t', 'x'],
                                           token_tensors={'t' : grids[0], 'x' : grids[1]},
                                           params_ranges = {'power' : (1, 1)},
                                           params_equality_ranges = None)        
    trig_tokens = TrigonometricTokens(dimensionality = dimensionality)
    
    
    epde_search_obj.create_pool(data = u, variable_names=['u'], max_deriv_order=(1, 3), 
                                           additional_tokens=[trig_tokens, custom_grid_tokens])

    return epde_search_obj.pool

def epde_discovery(x, t, u, use_ann = False):
    grids = np.meshgrid(t, x, indexing = 'ij')
    print(u.shape, grids[0].shape, grids[1].shape)
    multiobjective_mode = True
    dimensionality = u.ndim - 1
    
    epde_search_obj = epde_alg.EpdeSearch(multiobjective_mode=multiobjective_mode, use_solver = False, 
                                          dimensionality = dimensionality, boundary = 10,
                                          coordinate_tensors = grids)    
    
    if use_ann:
        epde_search_obj.set_preprocessor(default_preprocessor_type='ANN',
                                          preprocessor_kwargs={'epochs_max' : 20000})
    popsize = 7
    if multiobjective_mode:
        epde_search_obj.set_moeadd_params(population_size = popsize, 
                                          training_epochs=65)
    else:
        epde_search_obj.set_singleobjective_params(population_size = popsize, 
                                                   training_epochs=65)
    
    custom_grid_tokens = CacheStoredTokens(token_type = 'grid',
                                           token_labels = ['t', 'x'],
                                           token_tensors={'t' : grids[0], 'x' : grids[1]},
                                           params_ranges = {'power' : (1, 1)},
                                           params_equality_ranges = None)        
    trig_tokens = TrigonometricTokens(dimensionality = dimensionality)
    
    factors_max_number = {'factors_num' : [1, 2], 'probas' : [0.8, 0.2]}
    
    opt_val = 1e-1
    bounds = (1e-9, 1e0) if multiobjective_mode else (opt_val, opt_val)    
    print(u.shape, grids[0].shape)
    epde_search_obj.fit(data=u, variable_names=['u',], max_deriv_order=(2, 2),
                        equation_terms_max_number=5, data_fun_pow = 1, additional_tokens=[trig_tokens, custom_grid_tokens], 
                        equation_factors_max_number=factors_max_number,
                        eq_sparsity_interval=bounds)
    
    equation_obtained = False; compl = [4.5,]; attempt = 0
    
    iterations = 4
    while not equation_obtained:
        if attempt < iterations:
            try:
                sys = epde_search_obj.get_equations_by_complexity(compl)
                res = sys[0]
            except IndexError:
                compl[0] += 0.5
                attempt += 1
                continue
        else:
            res = epde_search_obj.equations(only_print = False)[0][0]
        equation_obtained = True
    return epde_search_obj, res

            
def sindy_provided_l0(grids, u):
    t = np.unique(grids[0])
    x = np.unique(grids[1])        
    u = u.T.reshape(len(x), len(t), 1)
    
    library_functions = [lambda x: x, lambda x: x * x]
    library_function_names = [lambda x: x, lambda x: x + x]
    pde_lib = ps.PDELibrary(
        library_functions=library_functions,
        function_names=library_function_names,
        derivative_order=3,
        spatial_grid=x,
        is_uniform=True,
    )    
    
    opt = 'SSR'
    if opt == 'FROLS':
        optimizer = ps.FROLS(normalize_columns=True, kappa=1e-3)    
    elif opt == 'STLSQ':
        optimizer = ps.STLSQ(threshold=2, alpha=1e-5, normalize_columns=True)
    elif opt == 'SR3':
        optimizer = ps.SR3(threshold=2,
                           max_iter=10000,
                           tol=1e-15,
                           nu=1e2,
                           thresholder="l0",
                           normalize_columns=True)
    elif opt == 'SSR':
        optimizer = ps.SSR(normalize_columns=True, kappa=1)
    model = ps.SINDy(feature_library=pde_lib, optimizer=optimizer)
    model.fit(u, t=dt)
    model.print()    
    return model


if __name__ == '__main__':
    path = 'C:\\Users\\Mike\\Documents\\Work\\EPDE\\projects\\wSINDy\\data\\data\\burgers\\'

    try:
        u_file = os.path.join(os.path.dirname( __file__ ), 'datasets/burgers/burgers.mat')
    except (FileNotFoundError, OSError):
        u_file = 'C:\\Users\\Mike\\Documents\\Work\\EPDE\\projects\\wSINDy\\data\\burgers\\burgers.mat'
    print(u_file)
    data = loadmat(u_file)

    t = np.ravel(data['t'])
    x = np.ravel(data['x'])
    u = np.real(data['usol']).T
    dt = t[1] - t[0]
    dx = x[1] - x[0]

    print(u.shape, t.shape)
    print(dt, dx)
    raise NotImplementedError()

    train_max = 51    
    grids = np.meshgrid(t, x, indexing = 'ij')
    grids_training = (grids[0][:train_max, ...], grids[1][:train_max, ...])
    grids_test = (grids[0][train_max:, ...], grids[1][train_max:, ...])    

    t_train, t_test = t[:train_max], t[train_max:]
    data_train, data_test = u[:train_max, ...], u[train_max:, ...]
    '''
    EPDE side
    '''

    run_epde = True
    run_sindy = True

    exps = {}
    test_launches = 5
    magnitudes = [0, 1.*1e-2, 2.5*1e-2, 5.*1e-2, 1.*1e-1, 1.5 * 1e-1, 2. * 1e-1, 2.5 * 1e-1]
    for magnitude in magnitudes:
        data_train_n = data_train + np.random.normal(scale = magnitude * np.abs(data_train), size = data_train.shape)
        
        errs_epde = []
        models_epde = []
        calc_epde = []
        pool = None
        
        if run_epde:
            for idx in range(test_launches):
                epde_search_obj, sys = epde_discovery(x, t_train, data_train_n, False)
                if pool is None:
                    pool = epde_search_obj.pool
        
                bnd_t = torch.cartesian_prod(torch.from_numpy(np.array([t[train_max + 1]], dtype=np.float64)),
                                              torch.from_numpy(x)).float()
                
                bop_1 = BOPElement(axis = 0, key = 'u_t', term = [None], power = 1, var = 0)
                bop_1.set_grid(bnd_t)
                bop_1.values = torch.from_numpy(data_test[0, ...]).float()
                
                t_der = epde_search_obj.saved_derivaties['u'][..., 0].reshape(grids_training[0].shape)
                bop_2 = BOPElement(axis = 0, key = 'dudt', term = [0], power = 1, var = 0)
                bop_2.set_grid(bnd_t)
                bop_2.values = torch.from_numpy(t_der[-1, ...]).float()
                
                bnd_x1 = torch.cartesian_prod(torch.from_numpy(t[train_max:]),
                                              torch.from_numpy(np.array([x[0]], dtype=np.float64))).float()
                bnd_x2 = torch.cartesian_prod(torch.from_numpy(t[train_max:]),
                                              torch.from_numpy(np.array([x[-1]], dtype=np.float64))).float()            
                
                bop_3 = BOPElement(axis = 1, key = 'u_x1', term = [None], power = 1, var = 0)
                bop_3.set_grid(bnd_x1)
                bop_3.values = torch.from_numpy(data_test[..., 0]).float()            
        
                bop_4 = BOPElement(axis = 1, key = 'u_x2', term = [None], power = 1, var = 0)
                bop_4.set_grid(bnd_x2)
                bop_4.values = torch.from_numpy(data_test[..., -1]).float()            
                
                pred_u_v = epde_search_obj.predict(system=sys, boundary_conditions=[bop_1(), bop_2(), bop_3(), bop_4()], 
                                                    grid = grids_test, strategy='NN')
                pred_u_v = pred_u_v.reshape(data_test.shape)
                models_epde.append(epde_search_obj)
                errs_epde.append(np.mean(np.abs(data_test - pred_u_v)))
                calc_epde.append(pred_u_v)
                
                try:
                    logger.add_log(key = f'Burgers_{magnitude}_attempt_{idx}', entry = sys, aggregation_key = ('sindy', magnitude),
                                   error_pred = np.mean(np.abs(data_test - pred_u_v)))
                except NameError:
                    logger = Logger(name = 'logs/Burgers_EPDE_high_noise.json', referential_equation = '0.1 * d^2u/dx2^2{power: 1.0} + 1.0 * u{power: 1.0} * du/dx2{power: 1.0}  + 0.0 = du/dx1{power: 1.0}', 
                                    pool = epde_search_obj.pool)
                    logger.add_log(key = f'Burgers_{magnitude}_attempt_{idx}', entry = sys, aggregation_key = ('sindy', magnitude),
                                   error_pred = np.mean(np.abs(data_test - pred_u_v)))
                 
            
        if run_sindy:
            if pool is None:
                pool = get_epde_pool(x, t_train, data_train_n)
            print(pool)
            model_base = sindy_provided_l0(grids_training, data_train_n)
            sys = translate_equation(translate_sindy_eq(model_base.equations()[0]), pool)
            
            solver_args = {'model' : None, 'use_cache' : True, 'dim': 2}#len(global_var.grid_cache.get_all()[1])}
            strategy = 'NN'
            
            adapter = SolverAdapter(var_number = len(sys.vars_to_describe))
            solution_model = adapter.solve_epde_system(system = sys, grids = grids_test, data = data_test, 
                                                       strategy = strategy)
            
            pred_u_v = solution_model(adapter.convert_grid(grids_test)).detach().numpy().reshape(data_test.shape)
            errs_sindy = np.mean(np.abs(data_test - pred_u_v))
            calc_sindy = pred_u_v
            try:
                logger.add_log(key = f'Burgers_sindy_{magnitude}', entry = sys, aggregation_key = ('sindy', magnitude), 
                               error_pred = np.mean(np.abs(data_test - pred_u_v)))
            except NameError:
                logger = Logger(name = 'logs/Burgers_SINDy_new.json', referential_equation = '0.1 * d^2u/dx2^2{power: 1.0} + 1.0 * u{power: 1.0} * du/dx2{power: 1.0}  + 0.0 = du/dx1{power: 1.0}', 
                                pool = pool)
                logger.add_log(key = f'Burgers_sindy_{magnitude}', entry = sys, aggregation_key = ('sindy', magnitude),
                               error_pred = np.mean(np.abs(data_test - pred_u_v)))

        else:
            model_base, errs_sindy, calc_sindy = None, None, None
        
        exps[magnitude] = {'epde': (models_epde, errs_epde, calc_epde),
                           'SINDy': (model_base, errs_sindy, calc_sindy)}
    logger.dump()