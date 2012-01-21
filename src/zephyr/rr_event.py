
import threading
import collections
import time

import zephyr.signal

def sign(value):
    return cmp(value, 0)

class RREventParser:
    def __init__(self, samplerate):
        self.samplerate = float(samplerate)
        self.received_value_count = 0
        self.latest_value_sign = 0
    
    def handle_values(self, values):
        for value in values:
            value_sign = sign(value)
            if value_sign != self.latest_value_sign:
                yield self.received_value_count / self.samplerate, abs(value)
            
            self.received_value_count += 1
            self.latest_value_sign = value_sign

class SignalCollectorWithRRProcessing(zephyr.signal.SignalCollector):
    def __init__(self):
        zephyr.signal.SignalCollector.__init__(self)
        self.rr_event_parser = None
        self.rr_events = []
    
    def handle_packet(self, signal_packet):
        zephyr.signal.SignalCollector.handle_packet(self, signal_packet)
        
        if signal_packet.type == "rr":
            if self.rr_event_parser is None:
                self.rr_event_parser = RREventParser(signal_packet.samplerate)
            
            rr_signal_start_timestamp = self.signal_streams["rr"].start_timestamp
            for relative_rr_event_timestamp, rr_event_value in self.rr_event_parser.handle_values(signal_packet.signal_values):
                rr_event_timestamp = relative_rr_event_timestamp + rr_signal_start_timestamp
                
                self.rr_events.append((rr_event_timestamp, rr_event_value))


class DelayedRealTimeStream(threading.Thread):
    def __init__(self, callback, delay=2.0):
        threading.Thread.__init__(self)
        self.callback = callback
        self.delay = delay
        self.rr_events_sent = 0
        self.signal_collector = zephyr.rr_event.SignalCollectorWithRRProcessing()
        
        self.stream_progresses = collections.defaultdict(lambda: 0)
    
    def handle_packet(self, signal_packet):
        self.signal_collector.handle_packet(signal_packet)
    
    def run(self):
        # Wait so that all signal streams have been initialized
        time.sleep(self.delay + 3.0)
        
        while True:
            delayed_current_time = time.time() - self.delay
            
            for stream_name, stream in self.signal_collector.signal_streams.items():
                stream_sample_index = int((delayed_current_time - stream.start_timestamp) * stream.samplerate)
                
                stream_progress = self.stream_progresses[stream_name]
                
                if stream_sample_index > stream_progress:
                    delayed_value = stream.signal_values[stream_sample_index]
                    self.callback(stream_name, delayed_value)
                    self.stream_progresses[stream_name] = stream_sample_index
            
            if len(self.signal_collector.rr_events) > self.rr_events_sent:
                rr_event_timestamp, rr_event_value = self.signal_collector.rr_events[self.rr_events_sent]
                
                if rr_event_timestamp <= delayed_current_time:
                    self.callback("rr_event", rr_event_value)
                    self.rr_events_sent += 1
            
            time.sleep(0.01)