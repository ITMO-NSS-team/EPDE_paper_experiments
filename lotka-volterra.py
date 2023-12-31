#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Mar 31 12:53:27 2023

@author: maslyaev
"""

import numpy as np
import time

import torch
import os

import matplotlib.pyplot as plt
import matplotlib

SMALL_SIZE = 12
matplotlib.rc('font', size=SMALL_SIZE)
matplotlib.rc('axes', titlesize=SMALL_SIZE)


from functools import reduce

import pysindy as ps

import epde.interface.interface as epde_alg
from epde.interface.solver_integration import BOPElement
from epde.interface.logger import Logger

from epde.interface.equation_translator import translate_equation

SOLVER_STRATEGY = 'autograd'

def write_pareto(dict_of_exp):
    for key, item in dict_of_exp.items():
        test_key = str(key[0]).replace('.', '_') + '__' + str(key[1]).replace('.', '_')
        with open('/home/maslyaev/epde/EPDE_main/projects/hunter-prey/param_var/'+test_key+'.txt', 'w') as f:
            for iteration in range(len(item)):
                f.write(f'Iteration {iteration}\n\n')
                for ind in [pareto.text_form for pareto in item[iteration][0]]:
                    f.write(ind + '\n\n')

def translate_sindy_eq(equation):
    print(equation)
    correspondence = {"0" : "u{power: 1.0}",
                      "0_1" : "du/dx1{power: 1.0}",
                      "1" : "v{power: 1.0}",
                      "1_1" : "dv/dx1{power: 1.0}",}
                        
     # Check EPDE translator input format
    
    def replace(term):
        term = term.replace(' ', '').split('x')
        for idx, factor in enumerate(term[1:]):
            try:
                if '^' in factor:
                    factor = factor.split('^')
                    term[idx+1] = correspondence[factor[0]].replace('{power: 1.0}', '{power: '+str(factor[1])+'.0}')
                else:
                    term[idx+1] = correspondence[factor]
            except KeyError:
                print(f'Key of term {factor} is missing')
                raise KeyError()
        return term
                
    if isinstance(equation, str):
        terms = []        
        split_eq = equation.split('+')
        const = split_eq[0][:-2]
        for term in split_eq[1:]:
            print('To replace:', term, replace(term))
            terms.append(reduce(lambda x, y: x + ' * ' + y, replace(term)))
        terms_comb = reduce(lambda x, y: x + ' + ' + y, terms) + ' + ' + const + ' = du/dx1{power: 1.0}'
        return terms_comb        
    elif isinstance(equation, list):
        assert len(equation) == 2
        var_list = ['u', 'v', 'w']
        eqs_tr = []
        for idx, eq in enumerate(equation):
            terms = []            
            split_eq = eq.split('+')
            const = split_eq[0][:-2]
            for term in split_eq[1:]:
                print('To replace:', term, replace(term))                
                terms.append(reduce(lambda x, y: x + ' * ' + y, replace(term)))
            terms_comb = reduce(lambda x, y: x + ' + ' + y, terms) + ' + ' + const + ' = d' + var_list[idx] + '/dx1{power: 1.0}'
            eqs_tr.append(terms_comb)
        print('Translated system:', eqs_tr)
        return eqs_tr
    else:
        raise NotImplementedError()

def get_epde_pool(t, x, y, use_ann = False):
    dimensionality = x.ndim - 1
    
    '''
    Подбираем Парето-множество систем дифф. уравнений.
    '''
    epde_search_obj = epde_alg.EpdeSearch(use_solver = False, dimensionality = dimensionality, boundary = 25,
                                           coordinate_tensors = [t,])
    if use_ann:
        epde_search_obj.set_preprocessor(default_preprocessor_type='ANN', # use_smoothing = True poly
                                         preprocessor_kwargs={'epochs_max' : 35000})# 
    else:
        epde_search_obj.set_preprocessor(default_preprocessor_type='poly', # use_smoothing = True poly
                                         preprocessor_kwargs={'use_smoothing' : True, 'sigma' : 1, 
                                                              'polynomial_window' : 3, 'poly_order' : 3}) # 'epochs_max' : 10000})# 
                                     # preprocessor_kwargs={'use_smoothing' : True, 'polynomial_window' : 3, 'poly_order' : 2, 'sigma' : 3})#'epochs_max' : 10000}) 'polynomial_window' : 3, 'poly_order' : 3
    popsize = 12
    epde_search_obj.set_moeadd_params(population_size = popsize, training_epochs=85)
    
    epde_search_obj.create_pool(data=[x, y], variable_names=['u', 'v'], max_deriv_order=(1,)) 
                                # additional_tokens=[trig_tokens, custom_grid_tokens])

    return epde_search_obj.pool

def epde_discovery(t, x, y, use_ann = False):
    dimensionality = x.ndim - 1
    epde_search_obj = epde_alg.EpdeSearch(use_solver = False, dimensionality = dimensionality, boundary = 25,
                                           coordinate_tensors = [t,])
    if use_ann:
        epde_search_obj.set_preprocessor(default_preprocessor_type='ANN', 
                                         preprocessor_kwargs={'epochs_max' : 35000}) 
    else:
        epde_search_obj.set_preprocessor(default_preprocessor_type='poly',
                                         preprocessor_kwargs={'use_smoothing' : True, 'sigma' : 1, 
                                                              'polynomial_window' : 3, 'poly_order' : 3}) # 'epochs_max' : 10000})# 
    popsize = 35
    epde_search_obj.set_moeadd_params(population_size = popsize, training_epochs=55)
    factors_max_number = {'factors_num' : [1, 2], 'probas' : [0.5, 0.5]}
    
    epde_search_obj.fit(data=[x, y], variable_names=['u', 'v'], max_deriv_order=(1,),
                        equation_terms_max_number=5, data_fun_pow = 2, #additional_tokens=[trig_tokens,], 
                        equation_factors_max_number=factors_max_number,
                        eq_sparsity_interval=(1e-12, 1e-4))

    epde_search_obj.equations(only_print = True, num = 1)
    equation_obtained = False; compl = [2.5, 2.5]; attempt = 0
    
    iterations = 4    
    while not equation_obtained:
        if attempt < iterations:        
            try:
                sys = epde_search_obj.get_equations_by_complexity(compl)
                res = sys[0]
            except IndexError:
                compl[attempt % 2] += 1
                attempt += 1
                continue
        else:
            res = epde_search_obj.equations(only_print = False)[0][0]
        equation_obtained = True
    return epde_search_obj, res
    

def sindy_discovery(t, x, y, sparsity = 0.05):
    poly_order = 2
    
    x_train = np.array([x, y]).T
    print(x_train.shape)
    
    model = ps.SINDy(
        optimizer=ps.STLSQ(alpha=sparsity),
        feature_library=ps.PolynomialLibrary(degree=poly_order),
    )
    model.fit(
        x_train,
        t=t[1] - t[0],
        quiet=True,
    )
    return model

def weak_sindy_discovery(t, x, y):
    dt = t[1] - t[0]
    x_train = np.array([x, y]).T
    print(x_train.shape)

    x_dot = ps.FiniteDifference()._differentiate(x_train, t=dt)
    model = ps.SINDy()
    model.fit(x_train, x_dot=x_dot, t=dt)
    model.print()    
    
    library_functions = [lambda x: x, lambda x: x * x, lambda x, y: x * y]
    library_function_names = [lambda x: x, lambda x: x + x, lambda x, y: x + y]
    ode_lib = ps.WeakPDELibrary(
        library_functions=library_functions,
        function_names=library_function_names,
        spatiotemporal_grid=t_train,
        is_uniform=True,
        K=10,
    )
    
    # Instantiate and fit the SINDy model with the integral of u_dot
    optimizer = ps.SR3(
        threshold=1.5, thresholder="l1", max_iter=1000, normalize_columns=True, tol=1e-1
    )
    model = ps.SINDy(feature_library=ode_lib, optimizer=optimizer)
    model.fit(x_train)
    model.print()
    return model


if __name__ == '__main__':
    '''
    Подгружаем данные, содержащие временные ряды динамики "вида-охотника" и "вида-жертвы"
    '''
    try:
        t_file = os.path.join(os.path.dirname( __file__ ), 'datasets/lotka_volterra/t_20.npy')
        t = np.load(t_file)
    except FileNotFoundError:
        t_file = '/home/maslyaev/epde/EPDE_main/projects/hunter-prey/t_20.npy'
        t = np.load(t_file)
    
    try:
        data_file =  os.path.join(os.path.dirname( __file__ ), 'datasets/lotka_volterra/data_20.npy')
        data = np.load(data_file)
    except FileNotFoundError:
        data_file = '/home/maslyaev/epde/EPDE_main/projects/hunter-prey/data_20.npy'
        data = np.load(data_file)
    
    large_data = False
    if large_data:
        t_max = 400; t_size_raw = 100; t_size_dense = 1000
        t_train = t[:t_max]; t_test = t[t_max:] 
        t_test_interval_pred = t_test

    else:
        t_max = 150
        t_train = t[:t_max]; t_test = t[t_max:] 
        t_test_interval_pred = t_test
        
    x = data[:t_max, 0]; x_test = data[t_max:, 0]
    y = data[:t_max, 1]; y_test = data[t_max:, 1]
    
    run_epde = True
    run_sindy = False
    pool = None
    
    exps = {}
    magnitudes = [0, 0.5*1e-2, 1.*1e-2, 2.5*1e-2, 5.*1e-2]#, 1.*1e-1, 1.5*1e-1]
    for magnitude in magnitudes:
        x_n = x + np.random.normal(scale = magnitude*x, size = x.shape)
        y_n = y + np.random.normal(scale = magnitude*y, size = y.shape)
        plt.plot(t_train, x_n)
        plt.plot(t_train, y_n)
        plt.show()
        
        test_launches = 10
        errs_epde = []
        models_epde = []
        calc_epde = []
        
        for idx in range(test_launches):
            if run_epde:
                t1 = time.time()
                epde_search_obj, system = epde_discovery(t_train, x_n, y_n, False)
                t2 = time.time()

                print('time_epde', t2-t1)
                def get_ode_bop(key, var, grid_loc, value):
                    bop = BOPElement(axis = 0, key = key, term = [None], power = 1, var = var)
                    bop_grd_np = np.array([[grid_loc,]])
                    bop.set_grid(torch.from_numpy(bop_grd_np).type(torch.FloatTensor))
                    bop.values = torch.from_numpy(np.array([[value,]])).float()
                    return bop
                    
                
                bop_x = get_ode_bop('u', 0, t_test_interval_pred[0], x_test[0])
                bop_y = get_ode_bop('v', 1, t_test_interval_pred[0], y_test[0])
                
                
                pred_u_v = epde_search_obj.predict(system=system, boundary_conditions=[bop_x(), bop_y()], 
                                                    grid = [t_test_interval_pred,], strategy=SOLVER_STRATEGY)
                plt.plot(t_test_interval_pred, x_test, '+', label = 'preys_odeint')
                plt.plot(t_test_interval_pred, y_test, '*', label = "predators_odeint")
                plt.plot(t_test_interval_pred, pred_u_v[..., 0], color = 'b', label='preys_NN')
                plt.plot(t_test_interval_pred, pred_u_v[..., 1], color = 'r', label='predators_NN')
                plt.xlabel('Время')
                plt.ylabel('Размер популяции')
                plt.grid()
                plt.legend(loc='upper right')
                plt.show()
                
                models_epde.append(epde_search_obj)
                err_u, err_v = np.mean(np.abs(x_test - pred_u_v[:, 0])), np.mean(np.abs(y_test - pred_u_v[:, 1]))
                errs_epde.append((err_u, err_v))
                calc_epde.append(pred_u_v)
                
                try:
                    logger.add_log(key = f'Lotka_Volterra_noise_{magnitude}_attempt_{idx}', entry = system, aggregation_key = ('epde', magnitude),
                                   error_pred = (err_u, err_v))
                except NameError:
                    logger = Logger(name = 'logs/lotka_volterra_new_EPDE.json', referential_equation = {'u' : '20.0 * u{power: 1.0} + -20.0 * u{power: 1.0} * v{power: 1.0} + 0.0 = du/dx1{power: 1.0}',
                                                                                                   'v' : '-20.0 * v{power: 1.0} + 20.0 * u{power: 1.0} * v{power: 1.0} + 0.0 = dv/dx1{power: 1.0}'}, 
                                    pool = epde_search_obj.pool)
                    logger.add_log(key = f'Lotka_Volterra_noise_{magnitude}_attempt_{idx}', entry = system, aggregation_key = ('epde', magnitude),
                                   error_pred = (err_u, err_v))
                            
        errs_SINDy = []
        models_SINDy = []
        calc_SINDy = []
        if run_sindy:            
            test_launches = 1
            for idx in range(test_launches):             
                '''
                Basic SINDy
                '''
                model_quality = np.inf; model_container = (None, None, None)
                for sparsity_thr in [50.,]: # 7., 12., ]: 
                    if pool is None:
                        pool = get_epde_pool(t_train, x_n, y_n)
                    print(pool)
                    t1 = time.time()                                           
                    model_base = sindy_discovery(t_train, x_n, y_n, sparsity=sparsity_thr)
                    t2 = time.time()
                    print('SINDy time', t2-t1)

                    print('Initial conditions', np.array([x_test[0], y_test[0]]))
                    eq_translated = translate_sindy_eq(model_base.equations())
                    system = translate_equation({'u': eq_translated[0],
                                              'v': eq_translated[1]}, pool)                    
                    print(system.text_form)
                    # try:
                    pred_u_v = model_base.simulate(np.array([x_test[0], y_test[0]]), t_test)
                    
                    plt.plot(t_test, x_test, '+', label = 'preys_odeint')
                    plt.plot(t_test, y_test, '*', label = "predators_odeint")
                    plt.plot(t_test, pred_u_v[:, 0], color = 'b', label='preys_NN')
                    plt.plot(t_test, pred_u_v[:, 1], color = 'r', label='predators_NN')
                    plt.xlabel('Time t, [days]')
                    plt.ylabel('Population')
                    plt.grid()
                    plt.legend(loc='upper right')
                    plt.title(f'Basic SINDy {magnitude}')
                    plt.show()
                    err_u, err_v = np.mean(np.abs(x_test - pred_u_v[:, 0])), np.mean(np.abs(y_test - pred_u_v[:, 1]))
                    if err_u + err_v < model_quality:
                        model_quality = err_u + err_v
                        model_container = (model_base, (err_u, err_v), pred_u_v)
    
                models_SINDy.append(model_container[0])
                errs_SINDy.append(model_container[1])
                calc_SINDy.append(model_container[2])                
                print('Discovered by SINDy:', system.text_form)
                
                try:
                    logger.add_log(key = f'Lotka_Volterra_SINDy_noise_{magnitude}_attempt_{idx}', entry = system, aggregation_key = ('sindy', magnitude), 
                                   error_pred = (err_u, err_v))
                except NameError:
                    logger = Logger(name = 'logs/lotka_volterra_new_SINDy.json', referential_equation = {'u' : '20.0 * u{power: 1.0} + -20.0 * u{power: 1.0} * v{power: 1.0} + 0.0 = du/dx1{power: 1.0}',
                                                                                                   'v' : '-20.0 * v{power: 1.0} + 20.0 * u{power: 1.0} * v{power: 1.0} + 0.0 = dv/dx1{power: 1.0}'}, 
                                    pool = pool)
                    logger.add_log(key = f'Lotka_Volterra_SINDy_noise_{magnitude}_attempt_{idx}', entry = system, aggregation_key = ('sindy', magnitude), 
                                   error_pred = (err_u, err_v))
 
        
                
        exps[magnitude] = {'epde': (models_epde, errs_epde, calc_epde), 
                           'SINDy' : (models_SINDy, errs_SINDy, calc_SINDy)}
    logger.dump()