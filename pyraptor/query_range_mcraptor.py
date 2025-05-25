"""Run range query on RAPTOR algorithm"""
import argparse
from typing import Dict, List
from copy import copy
from time import perf_counter

from loguru import logger

from pyraptor.dao.timetable import read_timetable
from pyraptor.model.structures import Timetable, Journey, pareto_set
from pyraptor.model.mcraptor import (
    McRaptorAlgorithm,
    best_legs_to_destination_station,
    reconstruct_journeys,
)
from pyraptor.util import sec2str
import json

def parse_arguments():
    """Parse arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="data/output",
        help="Input directory",
    )
    parser.add_argument(
        "-or",
        "--origin",
        type=str,
        default="207310",
        help="Origin station of the journey",
    )
    parser.add_argument(
        "-st",
        "--starttime",
        type=str,
        default="08:00:00",
        help="Start departure time (hh:mm:ss)",
    )
    parser.add_argument(
        "-et",
        "--endtime",
        type=str,
        default="08:30:00",
        help="End departure time (hh:mm:ss)",
    )
    parser.add_argument(
        "-r",
        "--rounds",
        type=int,
        default=5,
        help="Number of rounds to execute the RAPTOR algorithm",
    )
    arguments = parser.parse_args()

    return arguments


def main(
    input_folder: str,
    origin_station: str,
    rounds: int,
):
    """Run RAPTOR algorithm"""

    logger.debug("Input directory      : {}", input_folder)
    logger.debug("Origin station       : {}", origin_station)
    logger.debug("Rounds               : {}", str(rounds))

    timetable = read_timetable(input_folder)

    logger.info(f"Calculating network from : {origin_station}")

    # Find route between two stations for time range, i.e. Range Query
    journeys_to_destinations = run_range_mcraptor(
        timetable,
        origin_station,
        rounds,
    )

    # All destinations are calculated, however, we only print one for logging purposes
    for destination_station in journeys_to_destinations.keys():
        with open(f'data/output/optimal/{origin_station}_to_{destination_station}.json', 'w+') as f:
            output = []
            for jrny in journeys_to_destinations[destination_station]:
                journey_dict = jrny.serialize()
                output.append(journey_dict)
            json_output = json.dumps(output, indent=4) 
            f.write(json_output)


def run_range_mcraptor(
    timetable: Timetable,
    origin_station: str,
    max_rounds: int,
) -> Dict[str, List[Journey]]:
    """
    Perform the McRAPTOR algorithm for a range query
    """

    # Get stops for origins and destinations
    from_stops = timetable.stations.get_stops(origin_station)
    destination_stops = {
        st.name: timetable.stations.get_stops(st.id) for st in timetable.stations
    }
    destination_stops.pop(origin_station, None)

    # Find all trips leaving from stops within time range
    potential_trip_stop_times = timetable.trip_stop_times.get_trip_stop_times_in_range(
        from_stops
    )
    potential_dep_secs = sorted(
        list(set([tst.dts_dep for tst in potential_trip_stop_times])), reverse=True
    )

    logger.info(
        "Potential departure times : {}".format(
            [sec2str(x) for x in potential_dep_secs]
        )
    )

    journeys_to_destinations = {
        station_name: [] for station_name, _ in destination_stops.items()
    }

    logger.info("Calculating journeys to all destinations")
    s = perf_counter()
    # Find Pareto-optimal journeys for all possible departure times
    for dep_index, dep_secs in enumerate(potential_dep_secs):
        logger.info(f"Processing {dep_index} / {len(potential_dep_secs)}")
        logger.info(f"Analyzing best journey for departure time {sec2str(dep_secs)}")

        # Run Round-Based Algorithm
        mcraptor = McRaptorAlgorithm(timetable)
        if dep_index == 0:
            bag_round_stop, actual_rounds = mcraptor.run(from_stops, dep_secs, max_rounds)
        else:
            bag_round_stop, actual_rounds = mcraptor.run(from_stops, dep_secs, max_rounds, last_round_bag)
        last_round_bag = copy(bag_round_stop[actual_rounds])

        # Determine the best destination ID, destination is a platform
        for destination_station_name, to_stops in destination_stops.items():
            destination_legs = best_legs_to_destination_station(
                to_stops, last_round_bag
            )

            if len(destination_legs) != 0:
                journeys = reconstruct_journeys(
                    from_stops, destination_legs, bag_round_stop, k=actual_rounds
                )
                journeys_to_destinations[destination_station_name].extend(journeys)

    logger.info(f"Journey calculation time: {perf_counter() - s}")

    # Keep unique journeys
    for destination_station_name, journeys in journeys_to_destinations.items():
        unique_journeys = []
        for journey in journeys:
            if not journey in unique_journeys:
                unique_journeys.append(journey)

        journeys_to_destinations[destination_station_name] = unique_journeys
        
    return journeys_to_destinations


if __name__ == "__main__":
    args = parse_arguments()
    main(
        args.input,
        args.origin,
        args.rounds,
    )
