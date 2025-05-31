from enum import Enum

# How much SR does a player need to "promote" from one division to another? e.g. Diamond 1 -> Diamond 2
SKILL_RATING_PER_DIVISION = 100

# How many divisions per tier do we want? e.g. 3 -> Diamond I-III
DIVISIONS_PER_TIER = 3


class RankTier(Enum):
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"
    PLATINUM = "Platinum"
    DIAMOND = "Diamond"
    EXECUTIVE = "Executive"
    PRESIDENT = "President"


class Rank:

    def __init__(self, tier: RankTier, division: int):
        self.tier: RankTier = tier
        self.division: int = division

    def __roman(self) -> str:

        if self.division <= 0:
            return ''

        if 3 >= self.division >= 1:
            return 'I' * self.division

        if self.division == 4:
            return 'IV'

        if self.division == 5:
            return 'V'

        return str(self.division)

    def __str__(self):
        return f"{self.tier.value} {self.__roman()}".strip()

    def __repr__(self):
        return self.__str__()

    @classmethod
    def get_from_skill_rating(cls, skill_rating: int):
        """
        Computes a rank that matches the skill rating.
        This is a utility method that makes it very easy to determine someone's rank just off of a simple number.
        It should also be noted that you need to pass in a player's skill rating, and not their "mu value" or anything
        provided by openskill. Our "skill rating" value is something we track separately from mu, we just use openskill
        rating values to determine the +/- skill rating to adjust after every match.
        :param skill_rating: The skill rating. A value of 150 will return Bronze 2, and 350 will return Silver 1.

        :return: The rank that represents this skill rating.
        """

        # We can treat the rank divisions like an indexable array. Every 100 SR, we can go to the "next element".
        # We also should consider the edge case of being at "0 SR" for a rank. At 100 SR, we are at the exact bottom
        # of bronze 2, since a rank division is 0-99.
        element = skill_rating // SKILL_RATING_PER_DIVISION

        # Now that we have what "index" if all the divisions are lined up, determine the rank type.
        tiers = list(RankTier.__members__.values())
        index = element // DIVISIONS_PER_TIER

        # If we are out of bounds, it means that this player is very good! (president+)
        if index >= len(tiers):
            return Rank(RankTier.PRESIDENT, 0)

        # Otherwise, find their rank.
        tier: RankTier = tiers[index]

        # Presidents don't have a tier.
        if tier == RankTier.PRESIDENT:
            return Rank(RankTier.PRESIDENT, 0)

        # Calculate division. This can be calculated by subtracting the "skill rating" value of the base rank.
        rank_skill_rating_value = index * SKILL_RATING_PER_DIVISION * DIVISIONS_PER_TIER
        progress_in_tier = skill_rating - rank_skill_rating_value  # 0 represents SRs like Bronze 1 - 0SR
        division = progress_in_tier // SKILL_RATING_PER_DIVISION + 1
        return Rank(tier, division)
