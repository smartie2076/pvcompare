
.. _pv-feedin:

PV feedin - Modeling of different PV Technologies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*pvcompare* provides the possibility to calculate feed-in time series for the
following PV technologies under real world conditions:

a) flatplate silicon PV module (SI)
b) hybrid CPV (concentrator-PV) module: CPV cells mounted on a flat plate SI module (CPV)
c) multi-junction perovskite/silicon module (PeroSi)

While the SI module feed-in time series is completely calculated with `pvlib <https://pvlib-python.readthedocs.io/en/stable/index.html>`_ ,
unique models were developed for the CPV and PeroSi technologies. The next
sections will provide a detailed description of the different modeling
approaches.

1. SI
=====
The silicone module parameters are loaded from `cec module <https://github.com/NREL/SAM/tree/develop/deploy/libraries>`_ database. The module
selected by default is the "Aleo_Solar_S59y280" module with a 17% efficiency.
But any other module can be selected.

The time series is calculated by making usage of the `Modelchain  <https://pvlib-python.readthedocs.io/en/stable/modelchain.html>`_
functionality in `pvlib <https://pvlib-python.readthedocs.io/en/stable/index.html>`_. In order to make the results compareable for real world
conditions the following methods are selected from `modelchain object <https://pvlib-python.readthedocs.io/en/stable/api.html#modelchain>`_ :

- aoi_model="ashrae"
- spectral_model="first_solar"
- temperature_model="sapm"
- losses_model="pvwatts"

2. CPV
======

The CPV technology that is used in the *pvcompare* simulations is a hybrid
micro-Concentrator module with integrated planar tracking and diffuse light
collection of the company INSOLIGHT.
The following image describes the composition of the module.

.. _cpv_scheme:

.. figure:: ./images/scheme_cpv.png
    :width: 100%
    :alt: composition scheme of the hybrid module.
    :align: center

    composition scheme of the hybrid module. Direct beam irradiance is
    collected by 1mm III-V cells, while diffuse light is collected by
    the Si cell. For AOI not equal to 0°, the biconvex lens maintains
    a tight but translating focus. A simple mechanism causes the
    backplane to follow the focal point (see `Askins et al., 2019 <https://zenodo.org/record/3349781#.X46UFZpCT0o>`_).

"The Insolight technology employs a biconvex lens designed
such that focusing is possible when the angle of incidence
(AOI) approaches 60°, although the focal spot does travel as the
sun moves and the entire back plane is
translated to follow it, and maintain alignment. The back plane
consists of an array of commercial triple junction microcells
with approximately 42% efficiency combined with
conventional 6” monocrystalline Silicon solar cells. The
microcell size is 1mm and the approximate geometric
concentration ratio is 180X. Because the optical elements are
refractive, diffuse light which is not focused onto the III-V cells
is instead collected by the Si cells, which cover the area not
taken up by III-V cells. Voltages are not matched between III-
V and Si cells, so a four terminal output is provided." (`Askins et al., 2019 <https://zenodo.org/record/3349781#.X46UFZpCT0o>`_)

.. _hybrid_system:

Modeling the hybrid system
--------------------------
The model of the cpv technology is outsourced from *pvcompare* and can be found in the
`cpvlib <https://github.com/isi-ies-group/cpvlib>`_ repository. *pvcompare*
contains the wrapper function :py:func:`~pvcompare.cpv.apply_cpvlib_StaticHybridSystem.create_cpv_time_series`.

In order to model the dependencies of AOI, temperature and spectrum of the cpv
module, the model follows an approach of `[Gerstmeier, 2011] <https://www.researchgate.net/publication/234976094_Validation_of_the_PVSyst_Performance_Model_for_the_Concentrix_CPV_Technology>`_
previously implemented for CPV in *PVSYST*. The approach uses the single diode
model and adds so called "utilization factors" to the output power to account
losses due to spectral and lens temperature variations.

The utilization factors are defined as follows:

.. math::
    UF = \sum_{i=1}^{n} UF_i \cdot w_i

.. figure:: ./images/Equation_UF.png
    :width: 60%
    :align: center

    ".."

The overall model for the hybrid system is illustrated in the next figure.


.. figure:: ./images/StaticHybridSystem_block_diagram.png
    :width: 100%
    :align: center

    Modeling scheme of the hybrid micro-concentrator module
    (see `cpvlib on github <https://github.com/isi-ies-group/cpvlib>`_).

CPV submodule
-------------

Input parameters are weather data with AM (air mass), temperature,
DNI (direct normal irradiance), GHI (global horizontal irradiance) over time.
The CPV part only takes DNI into account. The angle of incidence (AOI) is calculated
by `pvlib.irradiance.aoi() <https://pvlib-python.readthedocs.io/en/stable/generated/pvlib.irradiance.aoi.html?highlight=pvlib.irradiance.aoi#pvlib.irradiance.aoi>`_.
Further the `pvlib.pvsystem.singlediode() <https://pvlib-python.readthedocs.io/en/stable/generated/pvlib.pvsystem.singlediode.html?highlight=singlediode>`_ function is solved for the given module parameters.
The utilization factors have been defined before by correlation analysis of
outdoor measurements. The given utilization factors for temperature and air mass
are then multiplied with the output power of the single diode functions. They
function as temperature and air mass corrections due to spectral and temperature
losses.

Flat plate submodule
--------------------

For AOI < 60° only the diffuse irradiance reaches the flat plate module:
GII (global inclined irradiance) - DII (direct inclined irradiance).
For Aoi > 60 ° also DII and DHI fall onto the flat plate module.
The single diode equation is then solved for all time steps with the specific
input irradiance. No module connection is assumed, so CPV and flat plate output
power are added up as in a four terminal cell.


Measurement Data
----------------
The Utilization factors were derived from outdoor measurement data of a three
week measurement in Madrid in May 2019. The Data can be found in
`Zenodo <https://zenodo.org/record/3346823#.X46UDZpCT0o>`_ ,
whereas the performance testing of the test module is described in `Askins, et al. (2019) <https://zenodo.org/record/3349781#.X46UFZpCT0o>`_.


2. PeroSi
=========
The perovskite-silicon cell is a high-efficiency cell that is still in its
test phase. Because perovskite is a material that is easily accessible many
researchers around the world are investigating the potential of single junction
perovskite and perovskite tandem cells cells, which we will focus on here.
Because of the early stage of the
development of the technology, no outdoor measurement data is available to
draw correlations for temperature dependencies or spectral dependencies which
are of great impact for multi-junction cells.

Modeling PeroSi
---------------

The following model for generating an output timeseries under real world conditions
is therefore based on cells that were up to now only tested in the laboratory.
Spectral correlations were explicitly calculated by applying `SMARTS <https://www.nrel.gov/grid/solar-resource/smarts.html>`_
(a Simple Model of the Atmospheric Radiative Transfer of Sunshine) to the given
EQE curves of our model. Temperature dependencies are covered by a temperature
coefficient for each sub cell. The dependence of AOI is taken into account
by `SMARTS <https://www.nrel.gov/grid/solar-resource/smarts.html>`_.
The functions for the following calculations can be found in the :ref:`psi` section.

.. figure:: ./images/schema_modell.jpg
    :width: 100%
    :alt: modeling scheme of the perovskite silicone tandem cell
    :align: center

    Modeling scheme of the perovskite silicone tandem cell.

Input data
----------

The following input data is needed:

* Weather data with DNI, DHI, GHI, temperature, wind speed
* Cell parameters for each sub cell:
    * Series resistance (R_s)
    * Shunt resistance (R_shunt)
    * Saturation current (j_0)
    * Temperature coefficient for the short circuit current (α)
    * Energy band gap
    * Cell size
    * External quantum efficiency curve (EQE-curve)

The cell parameters provided in *pvcompare* are for the cells (`[Korte2020] <https://pubs.acs.org/doi/10.1021/acsaem.9b01800>`_) ith 17 %
efficiency and (`[Chen2020] <https://www.nature.com/articles/s41467-020-15077-3>`_) bin 28.2% efficiency. For Chen the parameters R_s, R_shunt
and j_0 are evaluated by fitting the IV curve.

Modeling procedure
------------------
1. **weather data**
The POA_global (plane of array) irradiance is calculated with the `pvlib.irradiance.get_total_irradiance() <https://pvlib-python.readthedocs.io/en/stable/generated/pvlib.irradiance.get_total_irradiance.html#pvlib.irradiance.get_total_irradiance>`_ function

2. **SMARTS**
The `SMARTS <https://www.nrel.gov/grid/solar-resource/smarts.html>`_ spectrum is calculated for each time step.

2.1. the output values (``ghi_for_tilted_surface`` and
``photon_flux_for_tilted_surface``) are scaled with the ghi from `ERA5 <https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-pressure-levels?tab=overview>`_
weather data. The parameter ``photon_flux_for_tilted_surface`` scales linear to
the ``POA_global``.

2.2 the short circuit current (J_sc) is calculated for each time step:

.. math::
    Jsc = \int_\lambda EQE(\lambda) \cdot \Phi (\lambda) \cdot q d\lambda

    \text{with } \Phi : \text{photon flux for tilted surface}

    \text q : \text{elementary electric charge}

3. The `pvlib.pvsystem.singlediode() <https://pvlib-python.readthedocs.io/en/stable/generated/pvlib.pvsystem.singlediode.html?highlight=singlediode>`_
function is used to evaluate the output power of each
sub cell.

3.1 The output power Pmp is multiplied by the number of cells in series

3.2 Losses due to cell connection (5%) and cell to module connection (5%) are
taken into account.

4. The temperature dependency is accounted for by: (see `Jost et al., 2020 <https://onlinelibrary.wiley.com/doi/full/10.1002/aenm.202000454>`_)

.. math::
        Pmp = Pmp - Pmp \cdot \alpha  \cdot (T-T_0)

5. In order to get the module output the cell outputs are added up.


3. Normalization
================

For the energy system optimization normalized time series are needed, which can
then be scaled to the optimal installation size of the system.

There is three different ways to normalize the PV time series.

1) **Normalize by p_mp at standard test conditions (power at maximum powerpoint) (NSTC)**

* This procedure accounts for all losses under real world conditions and displays the difference between ideal operation and real world operation


2) **Normalize by p_mp at real world conditions (NRWC)**

* This procedure calculates the maximum power point for real world conditions at irr_ref = 1000 W/qm and temp_ref = 25°C.

* This way it treats the technology as if it was "ideal" under real world conditions.
* This normalization is of great importance when it comes to estimating technologies that are still under development and do not reach their reference p_mp yet.


3) **Normalize by peak according to intended module efficiency (NINT)**

* This procedure loads the *intended_efficiency* (Wp/m²) from module parameters and calculates the peak power according to the module size.
* This normalization is only to use for calculating the peak power for the nominal capacity and not for normalizing timeseries. The *intended_efficiency* can be changed in *module_parameters*.