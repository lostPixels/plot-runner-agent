from datetime import datetime, timedelta
import pytz

def calculate_end_time(job_duration, timezone_str='UTC'):
    """
    Calculate the end time in milliseconds by adding job_duration (in seconds) to the current time.

    :param job_duration: int, duration of the job in seconds
    :param timezone_str: str, timezone name (default is 'UTC')
    :return: int, milliseconds since Unix epoch representing the end time
    """
    # Get the timezone object
    timezone = pytz.timezone(timezone_str)

    # Get current time in the specified timezone
    current_time = datetime.now(timezone)

    # Calculate end time by adding job_duration
    end_time = current_time + timedelta(seconds=job_duration)

    # Convert to UTC and get milliseconds since epoch
    end_time_utc = end_time.astimezone(pytz.UTC)
    milliseconds = int(end_time_utc.timestamp() * 1000)

    return milliseconds
