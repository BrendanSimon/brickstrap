#!============================================================================
#! Settings file for efd_app
#!============================================================================

SERIAL_NUMBER="0"

SITE_NAME="Unit-Test"

PD_EVENT_TRIGGER_VOLTAGE=0.1

PD_EVENT_REPORTING_INTERVAL=300

#REPORTING_SMS_PHONE_NUMBERS=""
#REPORTING_SMS_PHONE_NUMBERS="+61417000000", "+61417000000"
REPORTING_SMS_PHONE_NUMBERS="+61470000000",

#! Server to ping to check internet connection is ok.
PING_SERVER="203.14.0.251"

#WEB_SERVER="http://efd.sepl.com.au"

TIMEZONE="Australia/Melbourne"

#! Set the web server address for posting data.
#WEB_SERVER="http://portal.efdweb.com"

#! Append gps, battery voltage, solar voltage and box temperature to measurements log.
#! NOTE: this is for testing the new web server that IND are developing !!
#! It will probably be a temporary settings !!
APPEND_GPS_DATA_TO_MEASUREMENTS_LOG=1

#!============================================================================
