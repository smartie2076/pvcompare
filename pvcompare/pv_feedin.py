"""
This module is designed for the use with the pvlib.

The weather data set has to be a DataFrame with the following columns:

pvlib:
 * ghi - global horizontal irradiation [W/m2]
 * dni - direct normal irradiation [W/m2]
 * dhi - diffuse horizontal irradiation [W/m2]
 * temp_air - ambient temperature [°C]
 * wind_speed - wind speed [m/s]
"""

from pvlib.location import Location
import pvlib.atmosphere
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
import pandas as pd
import os
import pvlib
import glob
import logging
import sys

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

import cpvtopvlib.cpvsystem as cpv
import greco_technologies.cpv.hybrid
import greco_technologies.cpv.inputs
from pvcompare import area_potential

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=log_format)

#import INS_CPV as ins

def create_pv_components(lat, lon, weather, population, pv_setup=None, plot=True,
                         input_directory=None, output_directory=None,
                         directory_energy_production=None):
    #todo: take nominal value and area potential to different function?
    """
    Reads pv_setup.csv; for each surface_type listed in pv_setup,
    one PV timeseries is created with regard to the technology and its
    orientation. All timeseries are normalized to the peak power of the
    module unsed and stored as csv files in ./data/mvs_inputs/sequences/pv.
    Further the area potential of the surface_type with regard to the building
    parameters defined in building_parameters.csv is calculated and the
    maximum installed capacity (nominal value) is calculated. Both parameters
    are stored into ./data/mvs_inputs/elements/csv/energyProduction.csv

    Parameters
    ----------
    lat: float
        latitude
    lon: float
        longitude
    population: num
        population
    pv_setup: dict
        with collumns: surface_type, technology, surface_azimuth, surface_tilt
        a tilt of 0 resembles a vertical orientation.
        if pv_setup=None loads example file data/pv/pv_setup.csvS
    plot: boolean
        if true plots created pv timeseries
    input_directory: str
        if None: ./data/inputs/
    output_directory: str
        if None: ./data/mvs_inputs/sequences/pv/
    directory_energy_production: str
        if None: ./data/mvs_inputs/elements/csv/

    Returns
    -------
    None
    """

    if pv_setup is None:
        # read example pv_setup file
        logging.info("loading pv setup conditions from input directory.")

        if input_directory is None:
            input_directory = 'data/inputs/'
        else:
         
                datapath = os.path.join(input_directory,
                                'pv_setup.csv')
        datapath = os.path.join(input_directory, 'pv_setup.csv')

        pv_setup=pd.read_csv(datapath)
        logging.info("setup conditions successfully loaded.")

    #empty output folder
    if output_directory is None:
        try:
            output_directory='data/mvs_inputs/sequences/pv/'
        except:
            logging.error("default output directory %s" % output_directory +
                          "cannot be found.")
    files = glob.glob(os.path.join(output_directory, "*"))

    for f in files:
        os.remove(f)

    #check if all three required columns are in pv_setup
    if not all([item in pv_setup.columns for item in ['surface_type',
                                                      'surface_azimuth',
                                                      'surface_tilt',
                                                      'technology']]):
        logging.error("The file pv_setup does not contain all required columns"
                      "surface_azimuth, surface_tilt and technology.")

    #check if mvs_input/energyProduction.csv contains all powerplants
    check_mvs_energy_production_file(pv_setup, directory_energy_production)
    # parse through pv_setup file and create timeseries for each technology
    for i, row in pv_setup.iterrows():
        j = row['surface_azimuth']
        k = row['surface_tilt']
        k = pd.to_numeric(k, errors='ignore')
        if k == "optimal":
            k = get_optimal_pv_angle(lat)
        if row["technology"]=="si":
            timeseries = create_si_timeseries(lat=lat, lon=lon,
                                                         weather=weather,
                                                         surface_azimuth=j,
                                                         surface_tilt=k)
        elif row["technology"]=="cpv":
            timeseries = create_cpv_timeseries(lat, lon,
                                                          weather,
                                                          j, k)
        elif row["technology"]=="psi":
            logging.error("The timeseries of psi cannot be calculated "
                          "yet. Please only use cpv or si right now.")
        else:
            logging.error(row["technology"], 'is not in technologies. Please '
                                             'chose si, cpv or psi.')
        # define the name of the output file of the timeseries
        output_csv=os.path.join(output_directory, str(row["technology"]) + '_'
                                + str(j) + '_' + str(k) + '.csv')
        # save timeseries into mvs_inputs
        timeseries.to_csv(output_csv)
        logging.info("%s" %row["technology"] + " timeseries is saved as csv "
                                               "into output directory")
        if plot == True:
            plt.plot(timeseries, label=str(row["technology"]) + str(j) + '_'
                                       + str(k),
                     alpha=0.7)
            plt.legend()
        #calculate area potential
        surface_type_list=['flat_roof', 'gable_roof', 'south_facade',
                           'east_facade', 'west_facade']
        if row['surface_type'] not in surface_type_list:
            logging.error("The surface_type in row %s" %i + " in pv_setup.csv"
                          " is not valid. Please choose from %s"
                          %surface_type_list)
        else:
            area=area_potential.calculate_area_potential(population,
                                                         input_directory,
                                 surface_type=row['surface_type'])

        #calculate nominal value of the powerplant
        nominal_value= nominal_values_pv(technology=row["technology"],
                                         area=area, surface_azimuth=j,
                                         surface_tilt=k)
        # save the file name of the timeseries and the nominal value to
        # mvs_inputs/elements/csv/energyProduction.csv
        add_parameters_to_energy_production_file(pp_number=i+1,
                                               ts_filename=output_csv,
                                               nominal_value=nominal_value, )

    if plot==True:
        plt.show()


def get_optimal_pv_angle(lat):

    """
    Calculates the optimal tilt angle depending on the latitude.

    e.G. about 27° to 34° from ground in Germany.
    The pvlib uses tilt angles horizontal=90° and up=0°. Therefore 90° minus
    the angle from the horizontal.
    """
    return round(lat - 15)


def set_up_system(technology, surface_azimuth, surface_tilt):

    """
    Initializes the pvlib.PVSystem for the given type of technology and returns
    the system and the module parameters as a dictionary.


    Parameters
    ----------
    technology: str
        possible technologies are: si, cpv or psi
    surface_azimuth: : float
        surface azimuth of the module
    surface_tilt: : float
        surface tilt of the module

    Returns
    -------
    PVSystem: pandas.Series
        Initialized PV system and module parameters.
    """

    if technology=="si":

        sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
        sandia_module = sandia_modules['Canadian_Solar_CS5P_220M___2009_']
        cec_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')
        cec_inverter = cec_inverters['ABB__MICRO_0_25_I_OUTD_US_208__208V_']
        system = PVSystem(surface_tilt=surface_tilt,
                          surface_azimuth=surface_azimuth,
                          module_parameters=sandia_module,
                          inverter_parameters=cec_inverter)

        return system, sandia_module

    elif technology=='cpv':

        logging.debug("cpv module parameters are loaded from "
                      "greco_technologies/inputs.py")
        module_params=greco_technologies.cpv.inputs.create_ins_dict()

        cpv_sys = cpv.StaticCPVSystem(surface_tilt=surface_tilt,
                                      surface_azimuth=surface_azimuth,
                                      module=None,
                                      module_parameters=module_params,
                                      modules_per_string=1,
                                      strings_per_inverter=1,
                                      inverter=None, inverter_parameters=None,
                                      racking_model='insulated',
                                      losses_parameters=None, name=None)

        return cpv_sys, module_params

    elif technology=='psi':
        logging.error('The nominal value for psi cannot be calculated yet.')
        pass

    else:
        logging.warning(technology, 'is not in technologies. Please chose si, '
                        'cpv or psi.')


def create_si_timeseries(lat, lon, weather, surface_azimuth,
                                    surface_tilt, normalized=True):

    r"""The cpv timeseries is created for a given weather dataframe, at a given
    orientation for the flat plate module 'Canadian_Solar_CS5P_220M___2009_'.
     The time series is normalized by the peak power of the module.

    Parameters
    ----------
    lat: float
        latitude
    lon: float
        longitude
    weather: pd.DataFrame
    surface_azimuth: float
        surface azimuth of the modules
    surface_tilt: float
        surface tilt of the modules
    normalized: boolean

    Returns
    -------
    pd.DataFrame
    """

    system, module_parameters=set_up_system(technology="si",
                                            surface_azimuth=surface_azimuth,
                                            surface_tilt=surface_tilt)
    location=Location(latitude=lat, longitude=lon)

    peak = module_parameters['Impo'] * module_parameters['Vmpo']

    mc = ModelChain(system, location, orientation_strategy=None,
                    aoi_model='sapm', spectral_model='sapm')
    mc.run_model(times=weather.index, weather=weather)
    output=mc.dc
    if normalized==True:
        logging.info("normalized si timeseries is calculated.")
        return (output['p_mp']/peak).clip(0)
    else:
        logging.info("si timeseries is calculated without normalization.")
        return output['p_mp']


def create_cpv_timeseries(lat, lon, weather, surface_azimuth,
                          surface_tilt, normalized=True):

    """The cpv timeseries is created for a given weather dataframe for the
    INSOLIGHT CPV module. If normalized=True the time series is normalized by
    the peak power of the module.

    Parameters
    ----------
    lat: float
        latitude
    lon: float
        longitude
    weather: pd.DataFrame
    surface_azimuth: float
        surface azimuth of the modules
    surface_tilt: float
        surface tilt of the modules
    normalized: boolean

    Returns
    -------
    pd.DataFrame
    """
    system, module_parameters=set_up_system(technology="cpv",
                                            surface_azimuth=surface_azimuth,
                                            surface_tilt=surface_tilt)

    peak = module_parameters['Impo'] * module_parameters['Vmpo']
    if normalized==True:
        logging.info("normalized cpv timeseries is calculated.")
        return (greco_technologies.cpv.hybrid.create_hybrid_timeseries(
            lat=lat, lon=lon, weather=weather, surface_tilt=25,
            surface_azimuth=180) / peak).clip(0)
    else:
        logging.info("cpv timeseries is calculated without normalization.")
        return greco_technologies.cpv.hybrid.create_hybrid_timeseries(
            lat=lat, lon=lon, weather=weather,
            surface_tilt=25, surface_azimuth=180)


#def create_psi_timeseries(lat, lon, weather, surface_azimuth, surface_tilt):


def nominal_values_pv(technology, area, surface_azimuth, surface_tilt):

    """
    The nominal value for each PV technology is constructed by the size of
    the module, its peak power and the total available area. The nominal value
    functions as a limit for the potential installed capacity of pv in oemof.

    Parameters
    ----------
    technology: str
        possible values are: si, cpv or psi
    area: float
        total available surface area
    surface_azimuth: float
        surface azimuth of the modules
    surface_tilt: float
        surface tilt of the modules

    Returns
    -------
    int
        the rounded possible installed capacity for an area
    """

    system, module_parameters = set_up_system(technology=technology,
                                              surface_azimuth=surface_azimuth,
                                              surface_tilt=surface_tilt)

    peak=module_parameters['Impo']*module_parameters['Vmpo']
    module_size= module_parameters['Area']
    nominal_value=round(area/module_size*peak)/1000
    logging.info('The nominal value for %s' %type + " is %s" %nominal_value +
                " kWp for an area of %s" %area + " qm.")
    return nominal_value


def check_mvs_energy_production_file(pv_setup, directory_energy_production=None,
                               overwrite=True):
    """
    This function compares the number of powerplants in
    data/mvs_inputs/elements/csv/energyProduction.csv with the number of rows
    in pv_setup.csv. If the number differs and overwrite=True, a new
    energyProduction.csv file is created with the correct number of columns and
    default values. The old file is overwritten. If overwrite=False, the
    process throws an error.


    Parameters
    ----------
    pv_setup: dict
    directory_energy_production: str
    overwrite: boolean

    Returns
    ---------
    None
    """



    if directory_energy_production==None:
        directory_energy_production= os.path.join(os.path.dirname(__file__),
                                          "data/mvs_inputs/elements/csv/")
    energy_production_filename= os.path.join(directory_energy_production,
                                            "energyProduction.csv")
    if os.path.isfile(energy_production_filename):
        energy_production = pd.read_csv(energy_production_filename,
                                        index_col=0)

        if len(energy_production.columns) - 1 == len(pv_setup.index):
            logging.info(
                "mvs_input file energyProduction.csv contains the correct"
                "number of pv powerplants.")
        elif overwrite == False:
            logging.error(
                "The number of pv powerplants in energyProduction.csv"
                " differs from the number of powerplants listed in "
                "pv_setup.csv. Please check energyProduction.csv or "
                "allow overwrite=True to have energyProduction.csv "
                "set up automatically with default values. ")
        else:
            logging.warning(
                "The number of pv powerplants in energyProduction.csv"
                " differs from the number of powerplants listed in "
                "pv_setup.csv. The file energyProduction.csv will thus "
                "be overwritten and created anew with default values.")
            create_mvs_energy_production_file(pv_setup, energy_production_filename)

    elif overwrite==False:
        logging.error("The file %s" %energy_production_filename + "does not"
                      "exist. Please create energyProduction.csv or "
                      "allow overwrite=True to have energyProduction.csv "
                      "set up automatically with default values.")
    else: logging.warning("The file %s" %energy_production_filename + "does not"
                          "exist. It will thus be created anew with default "
                          "values.")


def create_mvs_energy_production_file(pv_setup, energy_production_filename):

    """
    creates a new energyProduction.csv file with the correct number of pv
    powerplants as defined in pv_setup.py and saves it into ./data/mvs_inputs/
    elements/csv/energyProduction.csv

    Parameters
    ----------
    pv_setup: dict
    energy_production_filename: str

    Returns
    ---------
    None
    """
    #hardcoded list of parameters
    data = {'index': ["age_installed",
                    "capex_fix",
                    "capex_var",
                    "file_name",
                    "installedCap",
                    "label",
                    "lifetime",
                    "opex_fix",
                    "opex_var",
                    "optimizeCap",
                    "outflow_direction",
                    "type_oemof",
                    "unit",
                    "energyVector"],
            'unit': ['year',
                    'currency',
                    'currency/unit',
                    'str',
                    'kWp',
                    'str',
                    'year',
                    'currency/unit/year',
                    'currency/kWh',
                    'bool',
                    'str',
                    'str',
                    'str',
                    'str',
                    ]}
    df = pd.DataFrame(data, columns=['index', 'unit'])
    df.set_index('index', inplace=True)
    for i, row in pv_setup.iterrows():
        #hardcoded default parameters
        pp=['0',
                '10000',
                '7200',
                '0',
                '0',
                'PV plant (mono)',
                '30',
                '80',
                '0',
                'True',
                'PV plant (mono)',
                'source',
                'kWp',
                'Electricity']
        df['pv_plant_0' + str(i+1)] = pp

    df.to_csv(energy_production_filename)


def add_parameters_to_energy_production_file(pp_number, ts_filename,
                                            nominal_value,
                                            directory_energy_production=None):

    """
    enters the calculated installedCap and file_name parameters of one
    pv-powerplant in energyProduction.csv

    :param pp_number: int
        number of powerplants / columns in pv_setup
    :param ts_filename: str
        file name of the pv timeseries
    :param nominal_value: float
    :param directory_energy_production: str
    :return: None
    """

    if directory_energy_production==None:
        directory_energy_production= os.path.join(os.path.dirname(__file__),
                                          "data/mvs_inputs/elements/csv/")
    energy_production_filename= os.path.join(directory_energy_production,
                                            "energyProduction.csv")
    #load energyProduction.csv
    energy_production = pd.read_csv(energy_production_filename, index_col=0)
    #insert parameter values
    energy_production.loc[['installedCap'], ['pv_plant_0' + str(pp_number)]]=\
        nominal_value
    logging.info("The installed capacity of pv_plant_0%s" %pp_number +" has " \
                 "been added to energyProduction.csv.")
    energy_production.loc[['file_name'], ['pv_plant_0' + str(pp_number)]]=\
        ts_filename
    logging.info("The file_name of the time series of pv_plant_0%s" %pp_number
                 +" has been added to energyProduction.csv.")
    #save energyProduction.csv
    energy_production.to_csv(energy_production_filename)







if __name__ == '__main__':

    filename = os.path.abspath('/home/local/RL-INSTITUT/inia.steinbach/Dokumente/greco-project/pvcompare/pvcompare/data/ERA5_example_data_pvlib.csv')
    weather_df = pd.read_csv(filename, index_col=0,
                             date_parser=lambda idx: pd.to_datetime(idx,
                                                                    utc=True))
    weather_df.index = pd.to_datetime(weather_df.index).tz_convert(
        'Europe/Berlin')
    weather_df['dni']=weather_df['ghi']-weather_df['dhi']

    create_pv_components(lat=40.3, lon=5.4, weather=weather_df, pv_setup=None,
                         population=48000)



