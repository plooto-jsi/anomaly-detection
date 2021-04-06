from abc import abstractmethod
from abc import ABC
import json
import csv
from json import dumps
import os
from typing import Any, Dict
from kafka import KafkaProducer
#from kafka.admin import KafkaAdminClient, NewTopic


class OutputAbstract(ABC):
    send_ok: bool

    def __init__(self) -> None:
        pass

    @abstractmethod
    def configure(self, conf: Dict[Any, Any]) -> None:
        if("send_ok" in conf):
            self.send_ok = conf["send_ok"]
        else:
            self.send_ok = True

    @abstractmethod
    def send_out(self, value: Any, suggested_value: Any, status: str, timestamp: Any,
                 status_code: int = None, algorithm: str = "Unknown"
                 ) -> None:
        pass


class TerminalOutput(OutputAbstract):

    def __init__(self, conf: Dict[Any, Any] = None) -> None:
        super().__init__()
        if(conf is not None):
            self.configure(conf=conf)

    def configure(self, conf: Dict[Any, Any] = None) -> None:
        super().configure(conf=conf)
        # Nothing to configure
        pass

    def send_out(self,  value: Any, suggested_value: Any = None, 
                status: str = "", timestamp: Any = 0, status_code: int = None,
                algorithm: str = "Unknown") -> None:
        # Send to kafka only if an anomaly is detected (or if it is specified
        # that ok values are to be sent)
        if(status_code != 1 or self.send_ok):    
            o = str(timestamp) + ": " + status + "(value: " + str(value) + ")" + ", Algorithm: " + algorithm
            if(suggested_value is not None):
                o = o + ", Suggested value: " + str(suggested_value)
            print(o)


class FileOutput(OutputAbstract):
    file_name: str
    file_path: str
    mode: str

    def __init__(self, conf: Dict[Any, Any] = None) -> None:
        super().__init__()
        if(conf is not None):
            self.configure(conf=conf)

    def configure(self, conf: Dict[Any, Any] = None) -> None:
        super().configure(conf=conf)

        self.file_name = conf["file_name"]
        self.mode = conf["mode"]
        self.file_path = "log/" + self.file_name

        # make log folder if one does not exist
        dir = "./log"
        if not os.path.isdir(dir):
            os.makedirs(dir)

        # If mode is write clear the file
        if(self.mode == "w"):
            if(self.file_name[-4:] == "json"):
                with open(self.file_path, "w") as f:
                    d = {
                        "data": []
                    }
                    json.dump(d, f)
            elif(self.file_name[-3:] == "txt"):
                open(self.file_path, "w").close()
            elif(self.file_name[-3:] == "csv"):
                with open(self.file_path, "w", newline="") as csvfile:
                    fieldnames = ["timestamp", "status", "status_code", "value", "suggested_value", "algorithm"]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

    def send_out(self,  value: Any = None, suggested_value: Any = None,
                 status: str = "", timestamp: Any = None,
                 status_code: int = None, algorithm: str = "Unknown") -> None:

        # Send to kafka only if an anomaly is detected (or if it is specified
        # that ok values are to be sent)
        if(status_code != 1 or self.send_ok):
            if(self.file_name[-4:] == "json"):
                self.write_JSON(value=value, status=status,
                                timestamp=timestamp, status_code=status_code,
                                algorithm=algorithm,
                                suggested_value=suggested_value)
            elif(self.file_name[-3:] == "txt"):
                self.write_txt(value=value, status=status,
                            timestamp=timestamp, status_code=status_code,
                            algorithm=algorithm,
                            suggested_value=suggested_value)
            elif(self.file_name[-3:] == "csv"):
                self.write_csv(value=value, status=status,
                            timestamp=timestamp, status_code=status_code,
                            algorithm=algorithm,
                            suggested_value=suggested_value)
            else:
                print("Output file type not supported.")

    def write_JSON(self,  value: Any, timestamp: Any,
                   status: str = "", status_code: int = None,
                   algorithm: str = "Unknown", suggested_value: Any = None
                   ) -> None:
        # Construct the object to write
        to_write = {"algorithm": algorithm}
        if (value is not None):
            to_write["value"] = value
        if (status != ""):
            to_write["status"] = status
        if (timestamp is not None):
            to_write["timestamp"] = timestamp
        if (status_code is not None):
            to_write["status_code"] = status_code
        if(suggested_value is not None):
            to_write["suggested_value"] = suggested_value

        with open(self.file_path) as json_file:
            data = json.load(json_file)
            temp = data["data"]
            temp.append(to_write)
        with open(self.file_path, "w") as f:
            json.dump(data, f)

    def write_txt(self,  value: Any, status: str = "",
                  timestamp: Any = 0, status_code: int = None,
                  algorithm: str = "Unknown", suggested_value: Any = None
                  ) -> None:
        with open(self.file_path, "a") as txt_file:
            o = timestamp + ": " + status + "(value: " + str(value) + ")" + ", Algorithm: " + algorithm
            if(suggested_value is not None):
                o = o + ", Suggested value: " + suggested_value
            o = o + "\n"
            txt_file.write(o)

    def write_csv(self,  value: Any, status: str = "",
                  timestamp: Any = 0, status_code: int = None,
                  algorithm: str = "Unknown", suggested_value: Any = None
                  ) -> None:
        # Construct the object to write
        to_write = {"algorithm": algorithm}
        to_write["value"] = value
        to_write["status"] = status
        to_write["timestamp"] = timestamp
        to_write["status_code"] = status_code
        to_write["suggested_value"] = suggested_value

        with open(self.file_path, 'a', newline='') as csv_file:
            fieldnames = ["timestamp", "status", "status_code", "value", "suggested_value", "algorithm"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writerow(to_write)

class KafkaOutput(OutputAbstract):

    def __init__(self, conf: Dict[Any, Any] = None) -> None:
        super().__init__()
        # print(conf)
        if(conf is not None):
            self.configure(conf=conf)

    def configure(self, conf: Dict[Any, Any]) -> None:
        super().configure(conf=conf)
        self.node_id = conf['node_id']

        self.producer = KafkaProducer(bootstrap_servers=['localhost:9092'],
                         value_serializer=lambda x: 
                         dumps(x).encode('utf-8'))

    def send_out(self, suggested_value: Any,status: str = "",
                 timestamp: Any = None, status_code: int = None,
                value: Any = None,
                 algorithm: str = "Unknown") -> None:
        
        # Send to kafka only if an anomaly is detected (or if it is specified
        # that ok values are to be sent)
        if(status_code != 1 or self.send_ok):
            # Build a object to be sent out
            to_write = {"sensor": self.node_id}
            if(algorithm is not None):
                to_write["algorithm"] =algorithm
            if(status_code is not None):
                to_write["score"] = status_code
            if (timestamp is not None):
                to_write["timestamp"] = timestamp
            #if (value is not None):
            #    to_write["value"] = value
            if (status != ""):
                to_write["explanation"] = status
            
            kafka_topic = "anomalies_" + str(self.node_id)

            self.producer.send(kafka_topic, value=to_write)