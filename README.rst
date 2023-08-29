This is the repository, dedicated to the data-driven differential equation discovery experiments for the article, comparing the evolutionary-based approach and the sparsity-promoting one. We have developed an approach, employing equation structure detection via multi-objective evolutionary optimization (https://github.com/ITMO-NSS-team/EPDE). In the experiments we have used equation detection with sparse regression, implemented in SINDy framework (https://github.com/dynamicslab/pysindy).

Installation
============

EPDE framework can be installed from pypi with command:

.. code-block::

  $ pip install epde
  
or from github:

.. code-block::

  $ pip install git+https://github.com/ITMO-NSS-team/EPDE@main


For SINDy framework, various ways for installation are presented on the github page, with the simplest one being: 


.. code-block::

  $ pip install pysindy
