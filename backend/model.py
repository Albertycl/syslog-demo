
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.sqltypes import TIMESTAMP
db = SQLAlchemy()


def utc_8():
    return datetime.utcnow() + timedelta(hours=8)

# ***************************************************
class all_the_logs(db.Model):
    __tablename__ = "all_the_logs"
    id = db.Column(db.Integer, primary_key=True)
    # index=db.Column(db.String(255))
    timestamp=db.Column(db.DateTime)
    host_address=db.Column(db.String(255))
    host_name=db.Column(db.String(255))
    log_level=db.Column(db.String(255))
    message=db.Column(db.String(10000))
    service_type=db.Column(db.String(255))
    alert_acked_or_not=db.Column(db.String(255), default='alert_not_acked', server_default='alert_not_acked')
    escalate_to_net=db.Column(db.String(255), default='escalate', server_default='escalate')
    pause_the_alert_until_when=db.Column(db.DateTime)
    boolean_for_pausing_alert_checkbox=db.Column(db.Boolean, default=False, nullable=False)
    paused_by_which_folder=db.Column(db.String(255))
    who_acked_the_alert=db.Column(db.String(255))
    who_paused_the_alert=db.Column(db.String(255))
    which_keyword_is_triggered=db.Column(db.String(255))
    insert_by_which_condition=db.Column(db.String(255))
    

    @property
    def serialize(self):
        return {
            "id":self.id,
            "timestamp":f"{self.timestamp}",
            "host_address":self.host_address,
            "host_name":self.host_name,
            "log_level":self.log_level,
            "message":self.message,
            "service_type":self.service_type,
            "alert_acked_or_not":self.alert_acked_or_not,
            "escalate_to_net":self.escalate_to_net,
            "pause_the_alert_until_when":self.pause_the_alert_until_when,
            "boolean_for_pausing_alert_checkbox":self.boolean_for_pausing_alert_checkbox,
            "paused_by_which_folder":self.paused_by_which_folder,
            "who_acked_the_alert":self.who_acked_the_alert,
            "who_paused_the_alert":self.who_paused_the_alert,
            "which_keyword_is_triggered":self.which_keyword_is_triggered,
        }   

    @property
    def serialize_for_showing_which_alerts_has_been_paused(self):
        return {
            "id":self.id,
            "timestamp":f"{self.timestamp}",
            "host_address":self.host_address,
            "host_name":self.host_name,
            "log_level":self.log_level,
            "message":self.message,
            "service_type":self.service_type,
            "alert_acked_or_not":self.alert_acked_or_not,
            "pause_the_alert_until_when":f"{self.pause_the_alert_until_when}",
            "boolean_for_pausing_alert_checkbox":self.boolean_for_pausing_alert_checkbox,
            "paused_by_which_folder":self.paused_by_which_folder,
            "who_paused_the_alert":self.who_paused_the_alert,
        }   
        
        
    @property
    def serialize_show_latest_in_main_page(self):
        return {
            "timestamp":f"{self.timestamp}",
            "host_name":self.host_name,
        }   
                    
            
    




# # ***************************************************

class ingore_keyword(db.Model):
    __tablename__ = "ingore_keyword"
    id = db.Column(db.Integer, primary_key=True)
    device_name=db.Column(db.String(255))
    match_which_keyword=db.Column(db.String(255))
    filter_sub_keyword=db.Column(db.String(255))
    timestamp=db.Column(db.DateTime, default=utc_8)
    selected = db.Column(db.Boolean,default=False, nullable=False)
    

    @property
    def serialize(self):
        return {
            "device_name":self.device_name,
            "match_which_keyword":self.match_which_keyword,
            "filter_sub_keyword":self.filter_sub_keyword,
            "selected":self.selected,
        }   
    

# ***************************************************

class folder_list(db.Model):
    __tablename__ = "folder_list"
    id = db.Column(db.Integer, primary_key=True)
    folder_for_outer_layer=db.Column(db.String(255))
    folder_belongs_to_which_classification=db.Column(db.String(255))
    timestamp=db.Column(db.DateTime, default=utc_8)
    how_many_alert_for_this_folder=db.Column(db.Integer)
    how_many_alerts_need_to_escalate_to_net=db.Column(db.Integer,default=0)
    

    @property
    def serialize(self):
        return {
            "id":self.id,
            "folder_for_outer_layer":self.folder_for_outer_layer,
            "how_many_alert_for_this_folder":self.how_many_alert_for_this_folder,
            "how_many_alerts_need_to_escalate_to_net":self.how_many_alerts_need_to_escalate_to_net,
            
        }   

    @property
    def serialize2(self):
        return {
            "folder_for_outer_layer":self.folder_for_outer_layer,
        }          
        



# ***************************************************

class keyword_and_device_to_filter(db.Model):
    __tablename__ = "keyword_and_device_to_filter"
    id = db.Column(db.Integer, primary_key=True)
    keyword_to_filter=db.Column(db.String(255))
    device_to_filter=db.Column(db.String(255))
    current_in_which_folder=db.Column(db.String(255))
    decision_is_include_or_exclude=db.Column(db.String(255))
    timestamp=db.Column(db.DateTime, default=utc_8)
    

    @property
    def serialize(self):
        return {
            "id":self.id,
            "keyword_to_filter":self.keyword_to_filter,
            "device_to_filter":self.device_to_filter,
            "current_in_which_folder":self.current_in_which_folder,
            "decision_is_include_or_exclude":self.decision_is_include_or_exclude,
        }   



# ***************************************************

class device_and_severity(db.Model):
    __tablename__ = "device_and_severity"
    id = db.Column(db.Integer, primary_key=True)
    device_name=db.Column(db.String(255))
    severity_for_this_device=db.Column(db.String(255))
    timestamp=db.Column(db.DateTime, default=utc_8)
    

    @property
    def serialize(self):
        return {
            "severity_for_this_device":self.severity_for_this_device,
        }   


# ***************************************************

class severity_user_choosen(db.Model):
    __tablename__ = "severity_user_choosen"
    id = db.Column(db.Integer, primary_key=True)
    severity_that_user_selected =db.Column(db.String(255))
    device_name=db.Column(db.String(255))
    folder_name=db.Column(db.String(255))
    how_many_alert_for_this_device=db.Column(db.Integer)
    timestamp=db.Column(db.DateTime, default=utc_8)
    

    @property
    def serialize(self):
        return {
            "severity_that_user_selected":self.severity_that_user_selected,
            "device_name":self.device_name,
            "folder_name":self.folder_name,
        }   

    @property
    def serialize_device_name(self):
        return {
            "device_name":self.device_name,
        }  


    @property
    def serialize_list(self):
        return {
            "severity_that_user_selected":self.severity_that_user_selected.split(","),
            "device_name":self.device_name,
            "folder_name":self.folder_name,
        }                    


# ***************************************************

class predefine_severity(db.Model):
    __tablename__ = "predefine_severity"
    id = db.Column(db.Integer, primary_key=True)
    severity_for_the_device =db.Column(db.String(255))
    service_type =db.Column(db.String(255))
    # service_type is cisco or fortinet
    timestamp=db.Column(db.DateTime, default=utc_8)

    @property
    def serialize(self):
        return {
            "severity_for_the_device":self.severity_for_the_device,
            "service_type":self.service_type,
        }   

# ***************************************************

class fitler_condition_for_device_in_folder(db.Model):
    __tablename__ = "fitler_condition_for_device_in_folder"
    id = db.Column(db.Integer, primary_key=True)
    filter_for_which_device =db.Column(db.String(255))
    severity_that_user_choosen =db.Column(db.String(255))
    first_layer_is_contain_or_not_contain =db.Column(db.String(255))
    first_layer_filter_message =db.Column(db.String(255))
    second_layer_is_contain_or_not_contain =db.Column(db.String(255))
    second_layer_filter_message =db.Column(db.String(255))
    folder_name =db.Column(db.String(255))
    timestamp=db.Column(db.DateTime, default=utc_8)

    @property
    def serialize(self):
        return {
            "id":self.id,
            "folder_name":self.folder_name,
            "filter_for_which_device":self.filter_for_which_device,
            "severity_that_user_choosen":self.severity_that_user_choosen,
            "first_layer_is_contain_or_not_contain":self.first_layer_is_contain_or_not_contain,
            "first_layer_filter_message":self.first_layer_filter_message,
            "second_layer_is_contain_or_not_contain":self.second_layer_is_contain_or_not_contain,
            "second_layer_filter_message":self.second_layer_filter_message,
        
        }   




# # *******************************************
# class syslog_raw_data(db.Model):
#     __tablename__ = "syslog_raw_data"
#     id = db.Column(db.Integer, primary_key=True)

#     timestamp=db.Column(db.DateTime, default=datetime.now)
#     message_timestamp=db.Column(db.DateTime)
#     device_name=db.Column(db.String(255))
#     severity=db.Column(db.String(255))
#     description=db.Column(db.String(255))
#     event_id=db.Column(db.String(255))
#     message=db.Column(db.String(5000))
#     which_device=db.Column(db.String(255))
#     device_ip=db.Column(db.String(255))


#     @property
#     def serialize(self):
#         return {
#             "id":self.id,
#             "timestamp":f"{self.timestamp}",
#             "message_timestamp":f"{self.message_timestamp}",
#             "log_level":self.log_level,
#             "device_name":self.device_name,
#             "severity":self.severity,
#             "description":self.description,
#             "event_id":self.event_id,
#             "message":self.message,
#             "which_device":self.which_device,
#             "device_ip":self.device_ip,
#         }



# *******************************************

# class device_list(db.Model):
#     __tablename__ = "device_list"
#     id = db.Column(db.Integer, primary_key=True)
#     timestamp=db.Column(db.DateTime, default=datetime.now)
#     infra = db.Column(db.String(255))
#     ip = db.Column(db.String(255))
#     device_name = db.Column(db.String(255))
#     category = db.Column(db.String(255))
#     # does_the_infra_match_table_infra_list = db.Column(db.String(255))
  

#     @property
#     def serialize(self):
#         return {
#             "id": self.id,
#             "infra": self.infra,
#             "ip": self.ip,
#             "device_name": self.device_name,
#             "category": self.category,
#             "timestamp":f"{self.timestamp}",
        # }




class device_list(db.Model):
    __tablename__ = "device_list"
    id = db.Column(db.Integer, primary_key=True)
    index=db.Column(db.String(255))
    host_address=db.Column(db.String(255))
    host_name=db.Column(db.String(255))
    which_vendor=db.Column(db.String(255))
    deivce_belongs_to_which_folders=db.Column(db.String(255), default='device_doesnt_belong_to_any_folder', server_default='device_doesnt_belong_to_any_folder')
    device_folder=db.Column(db.String(255))   # role folder inside the infra: Routers, Switches, OOB, LTM, Firewall, Other
    timestamp=db.Column(db.DateTime, default=utc_8)
    

    @property
    def serialize(self):
        return {
            "host_address":self.host_address,
            "host_name":self.host_name,
        }   
    



class what_keyword_will_insert_db(db.Model):
    __tablename__ = "what_keyword_will_insert_db"
    id = db.Column(db.Integer, primary_key=True)
    timestamp=db.Column(db.DateTime, default=utc_8)   
    device_name=db.Column(db.String(255))
    device_ip=db.Column(db.String(255))
    contain_or_not_contain=db.Column(db.String(255))
    keyword_user_input=db.Column(db.String(255))
    selected = db.Column(db.Boolean,default=False, nullable=False)


    @property
    def serialize(self):
        return {
            "id":self.id,
            "device_name":self.device_name,
            "device_ip":self.device_ip,
            "contain_or_not_contain":self.contain_or_not_contain,
            "keyword_user_input":self.keyword_user_input,
            "selected":self.selected,
        }   
    


class auto_ack_which_device(db.Model):
    __tablename__ = "auto_ack_which_device"
    id = db.Column(db.Integer, primary_key=True)
    auto_ack_start_time=db.Column(db.DateTime)
    auto_ack_end_time=db.Column(db.DateTime)
    device_name=db.Column(db.String(255))
    
    
    @property
    def serialize(self):
        return {
            "id":self.id,
            "auto_ack_start_time":f"{self.auto_ack_start_time}",
            "auto_ack_end_time":f"{self.auto_ack_end_time}",
            "device_name":self.device_name,
        }   
        
        
        
class check_file_size(db.Model):
    __tablename__ = "check_file_size"
    id = db.Column(db.Integer, primary_key=True)
    file_size=db.Column(db.String(255))
    


# ***************************************************
class keyword_rule(db.Model):
    """A keyword rule with a scope. kind 'ignore' = never alert, 'alert' = always alert.
    infra/folder NULL means "all". The collectors read per-device rows (ingore_keyword,
    what_keyword_will_insert_db); this table remembers the scope so new devices get the rule too."""
    __tablename__ = "keyword_rule"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False)
    keyword = db.Column(db.String(255), nullable=False)
    infra = db.Column(db.String(32))
    folder = db.Column(db.String(255))
    vendor = db.Column(db.String(32))        # NULL = any vendor (cisco, LTM, paloalto, ...)
    timestamp = db.Column(db.DateTime, default=utc_8)


# ***************************************************
class collector_run(db.Model):
    """One run of the Elasticsearch collector (scheduled or manual), kept for the Collector runs page."""
    __tablename__ = "collector_run"
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=utc_8, index=True)
    duration_ms = db.Column(db.Integer)
    source = db.Column(db.String(16))            # schedule | manual
    ok = db.Column(db.Boolean, nullable=False, default=True)
    error_kind = db.Column(db.String(32))        # unreachable | timeout | certificate | auth | forbidden | server | other
    error_message = db.Column(db.String(500))
    minutes = db.Column(db.Integer)
    scanned = db.Column(db.Integer, default=0)
    matched = db.Column(db.Integer, default=0)
    unmatched = db.Column(db.Integer, default=0)
    new_alerts = db.Column(db.Integer, default=0)
    auto_acked = db.Column(db.Integer, default=0)
    ignored = db.Column(db.Integer, default=0)
    below_threshold = db.Column(db.Integer, default=0)
    already_stored = db.Column(db.Integer, default=0)
    details = db.Column(db.Text)                 # JSON: per-device counts, top unmatched senders, samples


# ***************************************************
class audit_log(db.Model):
    """Who changed what in the portal (every successful POST/PUT/DELETE)."""
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=utc_8, index=True)
    actor = db.Column(db.String(100), index=True)
    action = db.Column(db.String(48), index=True)       # e.g. alert.pause, device.add
    summary = db.Column(db.String(600))
    target_type = db.Column(db.String(32))
    target_id = db.Column(db.String(64))
    details = db.Column(db.Text)                        # JSON: request body, counts, sample alerts ...
    ip = db.Column(db.String(64))


# ***************************************************
class pause_rule(db.Model):
    """'Mute the same error': until `until`, new alerts from this device whose message matches `signature`
    are stored paused instead of alarming. The signature is the message without timestamps/ports/pids."""
    __tablename__ = "pause_rule"
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(255), index=True)
    device_ip = db.Column(db.String(64), index=True)      # rules are keyed by IP so devices sharing a name stay separate
    signature = db.Column(db.String(600))
    sample = db.Column(db.String(300))
    until = db.Column(db.DateTime)
    who = db.Column(db.String(100))
    created = db.Column(db.DateTime, default=utc_8)
