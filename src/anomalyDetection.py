from abc import abstractmethod, ABC
from typing import Any, Dict, List, Tuple, Union
import numpy as np
import pandas as pd
import sys
import logging
from statistics import mean
from datetime import datetime

sys.path.insert(0,'./src')
sys.path.insert(1, 'C:/Users/Matic/SIHT/anomaly_det/anomalyDetection/')
from output import OutputAbstract, TerminalOutput, FileOutput, KafkaOutput
from visualization import VisualizationAbstract, GraphVisualization,\
    HistogramVisualization, StatusPointsVisualization
from normalization import NormalizationAbstract, LastNAverage,\
    PeriodicLastNAverage


class AnomalyDetectionAbstract(ABC):
    configuration_location: str

    # needed if there are more anomaly detection algorithms
    algorithm_indx: int

    memory_size: int
    memory: List[List[Any]]
    averages: List[List[int]]
    periodic_averages: List[List[Tuple[int, List[int]]]]
    shifts: List[List[int]]
    time_features: List[str]
    name: str

    use_cols: List[int]
    input_vector_size: int
    outputs: List["OutputAbstract"]
    visualization: "VisualizationAbstract"
    normalization: "NormalizationAbstract"

    # Statuses
    UNDEFINED = "Undefined"
    ERROR = "Error"
    WARNING = "Warning"
    OK = "OK"

    # Status codes
    UNDEFIEND_CODE = 2
    ERROR_CODE = -1
    WARNING_CODE = 0
    OK_CODE = 1

    def __init__(self) -> None:
        # Logging configuration
        logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
        
        self.memory = []

    @abstractmethod
    def message_insert(self, message_value: Dict[Any, Any]) -> Any:
        # logging when message recieved (this line can be commented)
        logging.info("%s recieved message.", self.name)
        pass

    @abstractmethod
    def configure(self, conf: Dict[Any, Any],
                  configuration_location: str = None,
                  algorithm_indx: int = None) -> None:
        self.configuration_location = configuration_location
        
        # If algorithm is initialized from consumer kafka it has this
        # specified
        self.algorithm_indx = algorithm_indx
        
        # FEATURE CONSTRUCTION CONFIGURATION
        self.input_vector_size = conf["input_vector_size"]

        if("braila_fall_feature" in conf):
            self.braila_fall = conf["braila_fall_feature"]
        else:
            self.braila_fall = []
        
        if("averages" in conf):
            self.averages = conf["averages"]
        else:
            self.averages = []

        if("periodic_averages" in conf):
            self.periodic_averages = conf["periodic_averages"]
        else:
            self.periodic_averages = []

        if("shifts" in conf):
            self.shifts = conf["shifts"]
        else:
            self.shifts = []

        if("time_features" in conf):
            self.time_features = conf["time_features"]
        else:
            self.time_features = []

        # Finds the largest element among averages and shifts
        if(len(self.shifts) == 0):
            max_shift = 0
        else:
            max_shifts = []
            for shifts in self.shifts:
                if(len(shifts) == 0):
                    max_shifts.append(0)
                else:
                    max_shifts.append(max(shifts))
            max_shift = max(max_shifts)+1

        if (len(self.averages) == 0):
            max_average = 0
        else:
            max_averages = []
            for averages in self.averages:
                if(len(averages) == 0):
                    max_averages.append(0)
                else:
                    max_averages.append(max(averages))
            max_average = max(max_averages)

        if (len(self.periodic_averages) == 0):
            max_periodic_average = 0
        else:
            max_periodic_average = 0
            for feature_avgs in self.periodic_averages:
                for period_tuple in feature_avgs:
                    period = period_tuple[0]
                    # assumes period specifies at least one average
                    max_avg = max(period_tuple[1])
                    # Memory required to calculate the average
                    required_memory = 1+(period * (max_avg-1))
                    if(required_memory > max_periodic_average):
                        max_periodic_average = required_memory

        # one because of feature construction memory management
        self.memory_size = max(max_shift, max_average, max_periodic_average, 1)

        # OUTPUT/VISUALIZATION INITIALIZATION & CONFIGURATION
        self.outputs = [eval(o) for o in conf["output"]]
        output_configurations = conf["output_conf"]
        for o in range(len(self.outputs)):
            self.outputs[o].configure(output_configurations[o])
        if ("visualization" in conf):
            self.visualization = eval(conf["visualization"])
            visualization_configurations = conf["visualization_conf"]
            self.visualization.configure(visualization_configurations)
        else:
            self.visualization = None

        # NORMALIZATION INITIALIZATION & CONFIGURATION
        if("normalization" in conf):
            self.normalization = eval(conf["normalization"])
            normalization_configuration = conf["normalization_conf"]
            self.normalization.configure(normalization_configuration) 
        else:
            self.normalization = None
        
        # If specified save which columns to use
        if("use_cols" in conf):
            self.use_cols = conf["use_cols"]
        else:
            self.use_cols = None
    
    def check_ftr_vector(self, message_value: Dict[Any, Any]) -> bool:
        # Check for ftr_vector field
        if(not "ftr_vector" in message_value):
            logging.warning(f"{self.name}: ftr_vector field was not contained in message.")
            return False

        # Check for timestamp field
        if(not "timestamp" in message_value):
            logging.warning(f"{self.name}: timestamp field was not contained in message.")
            return False

        # Check vector length
        if(len(message_value["ftr_vector"]) != self.input_vector_size):
            logging.warning("%s: Given test value does not satisfy input vector size. Feature vector: %s",
                            self.name,
                            "[" + ",".join([str(elem) for elem in message_value["ftr_vector"]]) + "]")
            return False

        # Check if feature vector contains a string
        if(any(type(x)==str for x in message_value["ftr_vector"])):
            logging.warning(f"{self.name}: Feature vector contains a string.")
            return False

        # Check if feature vector contains None
        if(any(x==None for x in message_value["ftr_vector"])):
            logging.warning(f"{self.name}: Feature vector contains a None.")
            return False

        
        
        # Test if timestamp is of type int
        if(not isinstance(message_value["timestamp"], float)):
            logging.warning("%s: Timestamp not in correct format: %s",
                            self.name, message_value["timestamp"])
            return False

        # Test if timestamp is valid
        timestamp_ok = False
       
        try:
            pd.to_datetime(message_value["timestamp"], unit="s")
            timestamp_ok = True
        except(pd._libs.tslibs.np_datetime.OutOfBoundsDatetime):
            try:
                pd.to_datetime(message_value["timestamp"], unit="ms")
                timestamp_ok = True
            except(pd._libs.tslibs.np_datetime.OutOfBoundsDatetime):
                pass
        if(not timestamp_ok):
            logging.warning("%s: Invalid timestamp: %s", self.name,
                            message_value["timestamp"])
            return False
        
        return True

    def change_last_record(self, value: List[Any]) -> None:
        self.memory[-1] = value

    def training_feature_construction(self, data, timestamps) -> List[Any]:
        # Saves memory so it can be restored
        memory_backup = self.memory
        self.memory = []

        # Aditional feature construction
        features = []
        for i in range(len(data)):
            value = data[i].tolist()
            timestamp = timestamps[i]
            feature_vector = self.feature_construction(value=value,
                                                      timestamp=timestamp)

            if(feature_vector is not False):
                features.append(np.array(feature_vector))

        self.memory = memory_backup
        return features

    def feature_construction(self, value: List[Any], 
                             timestamp: str) -> Union[Any, bool]:

        # Add new value to memory and slice it
        self.memory.append(value)
        self.memory = self.memory[-self.memory_size:]

        if(len(self.memory) < self.memory_size):
            # The memory does not contain enough records for all shifts and 
            # averages to be created
            return False

        # create new value to be returned
        new_value = value.copy()

        # Create average features
        new_value.extend(self.average_construction())

        # Create periodic averages
        new_value.extend(self.periodic_average_construction())

        # Create shifted features
        new_value.extend(self.shift_construction())

        # Create time features
        new_value.extend(self.time_features_construction(timestamp))

        return new_value

    def average_construction(self) -> None:
        averages = []

        # Loop through all features
        for feature_index in range(len(self.averages)):
            # Loop through all horizons we want the average of
            for interval in self.averages[feature_index]:
                # Add last interval numbers to values array
                values = []
                for sample_indx in range(len(self.memory)):
                    if(sample_indx == interval):
                        break
                    values.append(self.memory[-(sample_indx+1)][feature_index])
                #print(values)
                averages.append(mean(values))

        return averages

    def periodic_average_construction(self) -> None:
        # construct periodic averages

        periodic_averages = []
        # Loop through features
        for feature_indx in range(len(self.periodic_averages)):
            # Loop through indexes for different features
            for period_indx in range(len(self.periodic_averages[feature_indx])):
                # Extract period and a list of how N-s (number of samples to
                # take from this sequence)
                period = self.periodic_averages[feature_indx][period_indx][0]
                averages = self.periodic_averages[feature_indx][period_indx][1]

                # Loop through N-s (number of samples to take from this
                # sequence)
                for average in averages:
                    # Construct a list of semples with this period from memory
                    periodic_list = []
                    # Loop through samples (in opposite direction) and if they
                    # are of right period add them to the list
                    for i in range(self.memory_size):
                        if(len(periodic_list) == average):
                            # Enough samples
                            break
                        if(i%period==0):
                            periodic_list.append(self.memory[self.memory_size-(i+1)][feature_indx])
                    
                    # print("periodic list:")
                    # print(periodic_list)
                    
                    # Append average of the list to features
                    avg = mean(periodic_list)
                    periodic_averages.append(avg)

        return periodic_averages

    def shift_construction(self) -> None:
        shifts = []

        # Loop through all features
        for feature_index in range(len(self.shifts)):
            # Loop through all shift values
            for look_back in self.shifts[feature_index]:
                shifts.append(self.memory[self.memory_size-(look_back+1)][feature_index])

        return shifts

    def time_features_construction(self, tmstp: Any) -> None:
        time_features = []

        try:
            dt = pd.to_datetime(tmstp, unit="s")
        except(pd._libs.tslibs.np_datetime.OutOfBoundsDatetime):
            dt = pd.to_datetime(tmstp, unit="ms")

        # Requires datetime format
        # Check for keywords specified in time_features
        if("month" in self.time_features):
            time_features.append(int(dt.month))
        if ("day" in self.time_features):
            time_features.append(int(dt.day))
        if ("weekday" in self.time_features):
            time_features.append(int(dt.weekday()))
        if ("hour" in self.time_features):
            time_features.append(int(dt.hour))
        if ("minute" in self.time_features):
            time_features.append(int(dt.minute))


        return time_features

    def normalization_output_visualization(self, status_code: int,
                                           status: str, value: List[Any],
                                           timestamp: Any) -> None:
        # Normalize if needed or just add the value
        normalized = None
        if(self.normalization is not None):
            if(status_code == -1):
                normalized = self.normalization.get_normalized(value=value)
                if(normalized != False):
                    self.change_last_record(value=normalized)
                else:
                    normalized = None
            else:
                self.normalization.add_value(value=value)
        
        for output in self.outputs:
            output.send_out(timestamp=timestamp, status=status,
                            suggested_value=normalized,
                            value=value,
                            status_code=status_code, algorithm=self.name)

        if(self.visualization is not None):
            lines = [value[0]]
            self.visualization.update(value=lines, timestamp=timestamp,
                                      status_code=status_code)
