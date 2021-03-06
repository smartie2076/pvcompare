"""
This module is designed for the use with the pvlib.

The weather data set has to be a DataFrame with the following columns:

pvlib:
 * ghi - global horizontal irradiation [W/m2]
 * dni - direct normal irradiation [W/m2]
 * dhi - diffuse horizontal irradiation [W/m2]
 * temp_air - ambient temperature [�C]
 * wind_speed - wind speed [m/s]
"""

from pvlib.location import Location
import pvlib.atmosphere
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
import pandas as pd
import os
import pvlib
import logging
import sys

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

import pvcompare.cpv.inputs
import pvcompare.perosi.perosi
from pvcompare import area_potential
from pvcompare import check_inputs
from pvcompare import constants

from cpvlib import cpvlib

from pvcompare.cpv import apply_cpvlib_StaticHybridSystem

log_format = "%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s"
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=log_format)


def create_pv_components(
    lat,
    lon,
    weather,
    population,
    year,
    pv_setup=None,
    plot=True,
    input_directory=None,
    mvs_input_directory=None,
    psi_type="Chen",
    normalization="NRWC",
):
    """
    Creates feed-in time series for all surface types in `pv_setup` or 'pv_setup.csv'.

    Reads 'pv_setup.csv', for each `surface_type` listed in `pv_setup`,
    one PV time series is created with regard to the technology and its
    orientation. All time series are normalized with the method specified in
    `normalization` and stored as csv files in `mvs_input_directory/time_series`.
    Further the area potential of the `surface_type` with regard to the building
    parameters defined in 'building_parameters.csv' in `input_directory` is calculated
    and the maximum installed capacity (nominal value) is calculated. Both parameters
    are stored into `mvs_input_directory/csv_elements/energyProduction.csv`.

    Parameters
    ----------
    lat: float
        latitude
    lon: float
        longitude
    population: num
        population
    pv_setup: dict or None
        Specifies the PV technologies and their installation details used in the
        simulation. The dictionary contains columns: surface_type, technology,
        surface_azimuth, surface_tilt.
        A tilt of 0 resembles a vertical orientation.
        If `pv_setup` is None, it is loaded from the `input_directory/pv_setup.cvs`.
    plot: bool
        if true plots created pv times series
    input_directory: str
        if None: ./data/inputs/
    mvs_input_directory: str
        if None: ./data/mvs_inputs/
    psi_type: str
        "Korte" or "Chen"
    normalization: str
        "NSTC": Normalize by reference p_mp
        "NRWC": Normalize by realworld p_mp
        None: no normalization


    Returns
    -------
    None
    """

    if pv_setup is None:
        # read example pv_setup file
        logging.info("loading pv setup conditions from input directory.")

        if input_directory is None:
            input_directory = constants.DEFAULT_INPUT_DIRECTORY

        data_path = os.path.join(input_directory, "pv_setup.csv")
        pv_setup = pd.read_csv(data_path)
        logging.info("setup conditions successfully loaded.")

    # check if all required columns are in pv_setup
    if not all(
        [
            item in pv_setup.columns
            for item in [
                "surface_type",
                "surface_azimuth",
                "surface_tilt",
                "technology",
            ]
        ]
    ):
        raise ValueError(
            "The file pv_setup does not contain all required columns"
            "surface_azimuth, surface_tilt and technology."
        )

    # check if mvs_input/energyProduction.csv contains all power plants
    check_inputs.check_mvs_energy_production_file(pv_setup, mvs_input_directory)

    #  define time series directory
    if mvs_input_directory is None:
        mvs_input_directory = constants.DEFAULT_MVS_INPUT_DIRECTORY
    time_series_directory = os.path.join(mvs_input_directory, "time_series")

    # parse through pv_setup file and create time series for each technology
    for i, row in pv_setup.iterrows():
        j = row["surface_azimuth"]
        k = row["surface_tilt"]
        k = pd.to_numeric(k, errors="ignore")
        if k == "optimal":
            k = get_optimal_pv_angle(lat)

        # check if timeseries already exists
        # define the name of the output file of the time series
        ts_csv = f"{row['technology']}_{j}_{k}_{year}_{lat}_{lon}.csv"
        output_csv = os.path.join(time_series_directory, ts_csv)

        if not os.path.isfile(output_csv):
            logging.info(
                "The timeseries does not exist yet and is therefore " "calculated."
            )

            if row["technology"] == "si":
                time_series = create_si_time_series(
                    lat=lat,
                    lon=lon,
                    weather=weather,
                    surface_azimuth=j,
                    surface_tilt=k,
                    normalization=normalization,
                )
            elif row["technology"] == "cpv":
                time_series = create_cpv_time_series(
                    lat=lat,
                    lon=lon,
                    weather=weather,
                    surface_azimuth=j,
                    surface_tilt=k,
                    normalization=normalization,
                )
            elif row["technology"] == "psi":
                time_series = create_psi_time_series(
                    lat=lat,
                    lon=lon,
                    year=year,
                    weather=weather,
                    surface_azimuth=j,
                    surface_tilt=k,
                    normalization=normalization,
                )
            else:
                raise ValueError(
                    row["technology"],
                    "is not in technologies. Please " "choose 'si', 'cpv' or " "'psi'.",
                )
            # create time series directory if it does not exists
            if not os.path.isdir(time_series_directory):
                os.mkdir(time_series_directory)

            # save time series into mvs_inputs
            time_series.fillna(0, inplace=True)
            time_series.to_csv(output_csv, header=["kW"], index=False)
            logging.info(
                "%s" % row["technology"] + " time series is saved as csv "
                "into output directory"
            )
        else:
            time_series = pd.read_csv(output_csv)
            logging.info(
                f"The timeseries {output_csv}"
                "already exists and is therefore not calculated again."
            )

        # add "evaluated_period" to simulation_settings.csv
        check_inputs.add_evaluated_period_to_simulation_settings(
            time_series=time_series, mvs_input_directory=mvs_input_directory
        )

        if plot == True:
            plt.plot(
                time_series,
                label=str(row["technology"]) + str(j) + "_" + str(k),
                alpha=0.7,
            )
            plt.legend()

        # calculate area potential
        surface_type_list = [
            "flat_roof",
            "gable_roof",
            "south_facade",
            "east_facade",
            "west_facade",
        ]
        if row["surface_type"] not in surface_type_list:
            raise ValueError(
                "The surface_type in row %s" % i + " in pv_setup.csv"
                " is not valid. Please choose from %s" % surface_type_list
            )
        else:
            area = area_potential.calculate_area_potential(
                population, input_directory, surface_type=row["surface_type"]
            )

        # calculate nominal value of the powerplant
        nominal_value = nominal_values_pv(
            technology=row["technology"],
            area=area,
            surface_azimuth=j,
            surface_tilt=k,
            psi_type=psi_type,
            normalization="NINT",
        )
        # save the file name of the time series and the nominal value to
        # mvs_inputs/elements/csv/energyProduction.csv
        check_inputs.add_parameters_to_energy_production_file(
            pp_number=i + 1,
            ts_filename=ts_csv,
            nominal_value=nominal_value,
            mvs_input_directory=mvs_input_directory,
        )
    if plot == True:
        plt.show()


def get_optimal_pv_angle(lat):

    """
    Calculates the optimal tilt angle depending on the latitude.

    e.G. about 27° to 34° from ground in Germany.
    The pvlib uses tilt angles horizontal=90° and up=0°. Therefore 90° minus
    the angle from the horizontal.

    Parameters
    ---------
    lat: float
        latitude

    Returns
    -------
    int
        rounded angle for surface tilt

    """
    return round(lat - 15)


def set_up_system(technology, surface_azimuth, surface_tilt):

    """
    Sets up pvlibPVSystems.

    Initializes the pvlib.PVSystem for the given type of technology and returns
    the system and the module parameters as a dictionary.


    Parameters
    ----------
    technology: str
        possible technologies are: si, cpv or psi
    surface_azimuth: float
        surface azimuth of the module
    surface_tilt: float
        surface tilt of the module

    Returns
    -------
    PVSystem: :pandas:`pandas.Series<series>`
        Initialized PV system and module parameters.
    """

    if technology == "si":

        sandia_modules = pvlib.pvsystem.retrieve_sam("cecmod")
        sandia_module = sandia_modules["Aleo_Solar_S59y280"]
        cec_inverters = pvlib.pvsystem.retrieve_sam("cecinverter")
        cec_inverter = cec_inverters["ABB__MICRO_0_25_I_OUTD_US_208__208V_"]
        system = PVSystem(
            surface_tilt=surface_tilt,
            surface_azimuth=surface_azimuth,
            module_parameters=sandia_module,
            inverter_parameters=cec_inverter,
        )

        return system, sandia_module

    elif technology == "cpv":

        logging.debug("cpv module parameters are loaded from pvcompare/cpv/inputs.py")
        mod_params_cpv = pvcompare.cpv.inputs.mod_params_cpv
        mod_params_flatplate = pvcompare.cpv.inputs.mod_params_flatplate

        static_hybrid_sys = cpvlib.StaticHybridSystem(
            surface_tilt=surface_tilt,
            surface_azimuth=surface_azimuth,
            module_cpv=None,
            module_flatplate=None,
            module_parameters_cpv=mod_params_cpv,
            module_parameters_flatplate=mod_params_flatplate,
            modules_per_string=1,
            strings_per_inverter=1,
            inverter=None,
            inverter_parameters=None,
            racking_model="insulated",
            losses_parameters=None,
            name=None,
        )

        return (static_hybrid_sys, mod_params_cpv, mod_params_flatplate)

    elif technology == "psi":
        pass
    else:
        logging.warning(
            f"{technology} is not in technologies. Please chose si, cpv or psi."
        )


def create_si_time_series(
    lat, lon, weather, surface_azimuth, surface_tilt, normalization
):

    """
    Calculates feed-in time series for a silicon PV module.

    The cpv time series is created for a given weather data frame, at a given
    orientation for the flat plate module 'Canadian_Solar_CS5P_220M___2009_'.
    If `normalization`is not None the time
    series is normalized according to the normalization method


    Parameters
    ----------
    lat: float
        latitude
    lon: float
        longitude
    weather: :pandas:`pandas.DataFrame<frame>`
    surface_azimuth: float
        surface azimuth of the modules
    surface_tilt: float
        surface tilt of the modules
    normalization: str
        "NSTC": Normalize by reference p_mp
        "NRWC": Normalize by realworld p_mp
        None: no normalization

    Returns
    -------
    :pandas:`pandas.Series<series>`
    """

    system, module_parameters = set_up_system(
        technology="si", surface_azimuth=surface_azimuth, surface_tilt=surface_tilt
    )
    location = Location(latitude=lat, longitude=lon)

    mc = ModelChain(
        system,
        location,
        orientation_strategy=None,
        aoi_model="ashrae",
        spectral_model="first_solar",
        temperature_model="sapm",
        losses_model="pvwatts",
    )

    mc.run_model(weather=weather)
    output = mc.dc
    if normalization is None:
        logging.info("Absolute si time series is calculated in kW.")
        return output["p_mp"] / 1000
    else:
        if normalization == "NINT":
            logging.warning(
                "The normalization option NINT should not be used "
                "to normalize timeseries. Please use a different "
                "option."
            )
        logging.info("Normalized SI time series is calculated in kW/kWp.")
        peak = get_peak(
            technology="si",
            normalization=normalization,
            module_parameters_1=module_parameters,
            module_parameters_2=None,
        )
        return (output["p_mp"] / peak).clip(0)


def create_cpv_time_series(
    lat, lon, weather, surface_azimuth, surface_tilt, normalization
):
    """
    Creates power time series of a CPV module.

    The CPV time series is created for a given weather data frame (`weather`)
    for the INSOLIGHT CPV module. If `normalization`is not None the time
    series is normalized according to the normalization method


    Parameters
    ----------
    lat : float
        Latitude of the location for which the time series is calculated.
    lon : float
        Longitude of the location for which the time series is calculated.
    weather : :pandas:`pandas.DataFrame<frame>`
        DataFrame with time series for temperature `temp_air` in C°, wind speed
        `wind_speed` in m/s, `dni`, `dhi` and `ghi` in W/m²
    surface_azimuth : float
        Surface azimuth of the modules (180° for south, 270° for west, etc.).
    surface_tilt: float
        Surface tilt of the modules. (horizontal=90° and vertical=0°)
    normalization: str
        "NSTC": Normalize by reference p_mp
        "NRWC": Normalize by realworld p_mp
        None: no normalization

    Returns
    -------
    :pandas:`pandas.Series<series>`
        Power output of CPV module in W.

    """

    system, mod_params_cpv, mod_params_flatplate = set_up_system(
        technology="cpv", surface_azimuth=surface_azimuth, surface_tilt=surface_tilt
    )

    if normalization is None:
        logging.info("Absolute CPV time series is calculated in kW.")
        return (
            apply_cpvlib_StaticHybridSystem.create_cpv_time_series(
                lat, lon, weather, surface_azimuth, surface_tilt
            )
            / 1000
        )

    else:

        if normalization == "NINT":
            logging.warning(
                "The normalization option NINT should not be used "
                "to normalize timeseries. Please use a different "
                "option."
            )
        logging.info("Normalized CPV time series is calculated in kW/kWp.")
        peak = get_peak(
            technology="cpv",
            normalization=normalization,
            module_parameters_1=mod_params_cpv,
            module_parameters_2=mod_params_flatplate,
        )
        return (
            apply_cpvlib_StaticHybridSystem.create_cpv_time_series(
                lat, lon, weather, surface_azimuth, surface_tilt
            )
            / peak
        ).clip(0)


def create_psi_time_series(
    lat,
    lon,
    year,
    surface_azimuth,
    surface_tilt,
    weather,
    normalization,
    psi_type="Chen",
):

    """
    Creates power time series of a Perovskite-Silicone module.

    The PSI time series is created for a given weather data frame
    (`weather`). If `normalization`is not None the time
    series is normalized according to the normalization method.


    Parameters
    ----------
    lat : float
        Latitude of the location for which the time series is calculated.
    lon : float
        Longitude of the location for which the time series is calculated.
    weather : :pandas:`pandas.DataFrame<frame>`
        DataFrame with time series for temperature `temp_air` in C°, wind speed
        `wind_speed` in m/s, `dni`, `dhi` and `ghi` in W/m^2
    surface_azimuth : float
        Surface azimuth of the modules (180° for south, 270° for west, etc.).
    surface_tilt: float
        Surface tilt of the modules. (horizontal=90° and vertical=0°)
    psi_type  : str
        Defines the type of module of which the time series is calculated.
        Options: "Korte", "Chen"
    normalization: str
        "NSTC": Normalize by reference p_mp
        "NRWC": Normalize by realworld p_mp
        None: no normalization

    Returns
    -------
    :pandas:`pandas.Series<series>`
        Power output of PSI module in W (if parameter `normalized` is False) or todo check unit.
        normalized power output of CPV module (if parameter `normalized` is
        False).

    """
    atmos_data = weather[
        ["ghi", "dhi", "dni", "wind_speed", "temp_air", "precipitable_water"]
    ]
    number_rows = atmos_data["ghi"].count()

    if normalization is None:
        logging.info("Absolute PSI time series is calculated in kW.")
        return (
            pvcompare.perosi.perosi.create_pero_si_timeseries(
                year,
                lat,
                lon,
                surface_azimuth,
                surface_tilt,
                atmos_data=atmos_data,
                number_hours=number_rows,
                psi_type=psi_type,
            )
            / 1000
        )
    else:
        if normalization == "NINT":
            logging.warning(
                "The normalization option NINT should not be used "
                "to normalize timeseries. Please use a different "
                "option."
            )
        logging.info("Normalized CPV time series is calculated in kW/kWp.")
        if psi_type == "Korte":
            import pvcompare.perosi.data.cell_parameters_korte_pero as param1
            import pvcompare.perosi.data.cell_parameters_korte_si as param2
        elif psi_type == "Chen":
            import pvcompare.perosi.data.cell_parameters_Chen_2020_4T_pero as param1
            import pvcompare.perosi.data.cell_parameters_Chen_2020_4T_si as param2

        peak = get_peak(
            technology="psi",
            normalization=normalization,
            module_parameters_1=param1,
            module_parameters_2=param2,
        )
        return (
            pvcompare.perosi.perosi.create_pero_si_timeseries(
                year,
                lat,
                lon,
                surface_azimuth,
                surface_tilt,
                atmos_data=atmos_data,
                number_hours=number_rows,
                psi_type=psi_type,
            )
            / peak
        ).clip(0)


def nominal_values_pv(
    technology, area, surface_azimuth, surface_tilt, psi_type, normalization="NINT"
):

    """
    calculates the maximum installed capacity for each pv module.

    The nominal value for each PV technology is constructed by the size of
    the module, its peak power and the total available area. It is given in
    the unit of kWp. The nominal value functions as a limit for the potential
    installed capacity of pv in oemof.

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
    normalization: str
        "NSTC": Normalize by reference p_mp
        "NRWC": Normalize by realworld p_mp
        "NINT": Normalize by intended efficiency. This option is only used to
        calculate the nominal value.

    Returns
    -------
    int
        the rounded possible installed capacity for an area
    """

    if technology == "si":
        system, module_parameters = set_up_system(
            technology=technology,
            surface_azimuth=surface_azimuth,
            surface_tilt=surface_tilt,
        )
        peak = get_peak(
            technology,
            normalization=normalization,
            module_parameters_1=module_parameters,
            module_parameters_2=None,
        )
        module_size = module_parameters["A_c"]
        nominal_value = round((area / module_size) * peak) / 1000
    elif technology == "cpv":
        system, mod_params_cpv, mod_params_flatplate = set_up_system(
            technology=technology,
            surface_azimuth=surface_azimuth,
            surface_tilt=surface_tilt,
        )
        peak = get_peak(
            technology,
            normalization=normalization,
            module_parameters_1=mod_params_cpv,
            module_parameters_2=mod_params_flatplate,
        )
        module_size = mod_params_cpv["Area"]
        nominal_value = round((area / module_size) * peak) / 1000
    elif technology == "psi":
        if psi_type == "Korte":
            import pvcompare.perosi.data.cell_parameters_korte_pero as param1
            import pvcompare.perosi.data.cell_parameters_korte_si as param2
        elif psi_type == "Chen":
            import pvcompare.perosi.data.cell_parameters_Chen_2020_4T_pero as param1
            import pvcompare.perosi.data.cell_parameters_Chen_2020_4T_si as param2

        # calculate peak power with 5 % CTM losses nad 5 % cell connection losses
        peak = get_peak(
            technology,
            normalization=normalization,
            module_parameters_1=param1,
            module_parameters_2=param2,
        )
        module_size = param1.A / 10000  # in m^2
        nominal_value = round((area / module_size) * peak) / 1000

    logging.info(
        "The nominal value for %s" % technology
        + " is %s" % nominal_value
        + " kWp for an area of %s" % area
        + " qm."
    )
    return nominal_value


def get_peak(technology, normalization, module_parameters_1, module_parameters_2):
    """
    this function returns the peak value for the given technology and the given
    type of normalization.

    Parameter
    ---------
    technology: str
        "si", "cpv" or "psi"
    normalization: str
        "NSTC": Normalize by reference p_mp
        "NRWC": Normalize by realworld p_mp
        "NINT": Normalize by intended efficiency. This option is only used to
        calculate the nominal value.
        None: no normalization
    module_parameters_1: dict
        module parameters of cell 1 or module
    module_parameters_2: dict
        if technology == si, set parameter to None
    psi_type: str
        "Korte" or "Chen"

    Returns
    --------
    numeric
        peak value used for normalization
    """

    if normalization == "NSTC":
        if technology == "si":
            peak = module_parameters_1["I_mp_ref"] * module_parameters_1["V_mp_ref"]
            return peak
        elif technology == "cpv":
            peak = (module_parameters_1["i_mp"] * module_parameters_1["v_mp"]) + (
                module_parameters_2["i_mp"] * module_parameters_2["v_mp"]
            )
            return peak
        elif technology == "psi":
            # calculate peak power with 10 % CTM losses
            peak = (module_parameters_1.p_mp + module_parameters_1.p_mp) - (
                (module_parameters_2.p_mp + module_parameters_2.p_mp) / 100
            ) * 10
            return peak
    elif normalization == "NRWC":
        return calculate_NRWC_peak(technology=technology)
    elif normalization == "NINT":
        if technology == "si":
            peak = module_parameters_1["I_mp_ref"] * module_parameters_1["V_mp_ref"]
            return peak
        elif technology == "cpv":
            peak = (
                module_parameters_1["Area"]
                * module_parameters_1["intended_efficiency"]
                * 10
            )
            return peak
        elif technology == "psi":
            peak = (
                (module_parameters_1.A / 10000)
                * module_parameters_1.intended_efficiency
                * 10
            )
            return peak


def calculate_NRWC_peak(technology):
    """
    calculates the peak value of a technology under real world conditions.

    Using weather year of Berlin, Germany, 2014 the dataframe is filtered to find
    the timestep where irradiance (poa_global) and cell temperature come
    closest to reference conditions of ghi=1000 W/m and temp_air= 25 °C.
    The p_mp at this timestep is taken as the reference peak value for normalization.

    Parameters
    ---------
    technology: str
        `si`, `cpv` or `psi`
    Returns
    --------
    numeric
        peak value
    """

    irr_ref = 1000
    temp_ref = 25
    lat = 52.52437
    lon = 13.41053
    year = 2014
    surface_tilt = get_optimal_pv_angle(lat=lat)

    input_directory = constants.DEFAULT_INPUT_DIRECTORY
    weather_file = os.path.join(
        input_directory, "weatherdata_52.52437_13.41053_2014.csv"
    )
    if os.path.isfile(weather_file):
        weather = pd.read_csv(weather_file, index_col=0)
    else:
        logging.error(
            f"the weather file {weather_file} does not exist. Please"
            f"make sure the weather file is in {input_directory}."
        )
    weather.index = pd.to_datetime(weather.index, utc=True)
    # calculate poa_global for tilted surface
    spa = pvlib.solarposition.spa_python(
        time=weather.index, latitude=lat, longitude=lon
    )
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=180,
        solar_zenith=spa["zenith"],
        solar_azimuth=spa["azimuth"],
        dni=weather["dni"],
        ghi=weather["ghi"],
        dhi=weather["dhi"],
    )
    weather["poa_global"] = poa["poa_global"]

    # calculate cell temperature
    weather["cell_temperature"] = pvlib.temperature.pvsyst_cell(
        poa_global=weather["poa_global"],
        temp_air=weather["temp_air"],
        wind_speed=weather["wind_speed"],
    )
    cell_temp = weather["cell_temperature"]
    irrad = weather["poa_global"]

    # filter weather data for poa_global = irr_ref
    # filter weather data for temperature = temp_ref
    peak_irr = weather.iloc[(weather["poa_global"] - irr_ref).abs().argsort()[:2]]
    peak_hour = peak_irr.iloc[
        (peak_irr["cell_temperature"] - temp_ref).abs().argsort()[:1]
    ]

    if technology == "si":

        timeseries = create_si_time_series(
            lat=lat,
            lon=lon,
            weather=peak_hour,
            surface_azimuth=180,
            surface_tilt=surface_tilt,
            normalization=None,
        )

    elif technology == "cpv":
        timeseries = create_cpv_time_series(
            lat=lat,
            lon=lon,
            weather=peak_hour,
            surface_azimuth=180,
            surface_tilt=surface_tilt,
            normalization=None,
        )

    elif technology == "psi":
        timeseries = create_psi_time_series(
            lat=lat,
            lon=lon,
            weather=peak_hour,
            surface_azimuth=180,
            surface_tilt=surface_tilt,
            normalization=None,
            psi_type="Chen",
            year=year,
        )

    logging.info(
        f"The timeseries of technology {technology} is normalized with"
        f"a peak power of {timeseries[0]} kW at reference conditions of"
        f"poa_global: {irrad} and cell_temp: {cell_temp} ."
    )
    # return peak power in Watts
    return timeseries[0] * 1000


if __name__ == "__main__":

    peak = calculate_NRWC_peak(technology="psi")
    print(peak)
