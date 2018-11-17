
def convert_epoch_to_datetime(epoch_time):
    from datetime import datetime

    epoch_in_sec = float(epoch_time)
    date = datetime.fromtimestamp(epoch_in_sec)

    return date
