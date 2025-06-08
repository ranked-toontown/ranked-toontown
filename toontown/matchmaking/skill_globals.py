from openskill.models import PlackettLuce, PlackettLuceRating

from toontown.matchmaking.zero_sum_elo_model import ZeroSumEloModel, ZeroSumEloRating

# The starting SR and hidden MMR for a player to default to if they are new.
STARTING_RATING = 1000
# The starting uncertainty rating for a player to default to if they are new. Should be default rating / 3.
STARTING_UNCERTAINTY = STARTING_RATING / 3

# The base SR rate for winning and losing. Modified based on the context of the game using this as a base.
BASE_SR_CHANGE = 20

# Define the model you want to use here.
# You can view the different models available here: https://openskill.me/en/stable/manual.html#picking-models
# You can also customize the inner workings on skill estimation, but the defaults are probably fine.
MODEL_CLASS = PlackettLuce
MODEL = MODEL_CLASS()
RATING_CLASS = PlackettLuceRating  # Update this to be whatever rating classes MODEL will return

# A custom model to use specifically for 1v1 matches. 1v1s use a zero-sum ELO system for hidden MMR.
ZERO_SUM_MODEL = ZeroSumEloModel(k_factor=32)
ZERO_SUM_RATING_CLASS = ZeroSumEloRating