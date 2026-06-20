"""20 complex raw-dictation samples for benchmarking local LLM cleanup/formatting.

Each `raw` string is the kind of messy, unpunctuated, filler-laden text a
speech-to-text engine produces. `expect` is a short human note on what good
structuring looks like (used for qualitative scoring, not automated grading).
"""

CASES = [
    {"id": 1, "expect": "list of 3 action items",
     "raw": "so basically what i wanted to say is that we need to finish the report by friday and also we should probably loop in the marketing team and oh yeah dont forget to book the conference room for the review meeting"},
    {"id": 2, "expect": "clean technical prose",
     "raw": "um the the api keeps returning a 500 error when i send a post request to the users endpoint but it works fine for get requests so i think theres something wrong with how we handle the request body maybe its the json parsing"},
    {"id": 3, "expect": "narrative prose, maybe inline list of items bought",
     "raw": "i went to the store today and i bought milk eggs bread and then i realized i forgot my wallet so i had to go back home and get it and then come back it was super annoying"},
    {"id": 4, "expect": "polite email request, 3 asks",
     "raw": "can you send me the the quarterly numbers when you get a chance also i need the the breakdown by region and if possible the year over year comparison thanks"},
    {"id": 5, "expect": "two date/time options, clearly formatted",
     "raw": "the meeting is scheduled for march 3rd at 2 30 pm in the main office but if that doesnt work we can also do it on the 5th at 10 am just let me know which one works better for you"},
    {"id": 6, "expect": "numbered list of 5 steps",
     "raw": "okay so the the plan is first we gather all the requirements then we do a design review after that development starts and finally we have testing and deployment"},
    {"id": 7, "expect": "bulleted list of 3 issues",
     "raw": "honestly i think the the new feature is great but theres a few issues like the loading is kind of slow and the the button placement is a bit weird and some users said the colors are hard to read"},
    {"id": 8, "expect": "prose; note: 'pacific' is an ASR homophone error for 'specific' (LLM ceiling case)",
     "raw": "i was thinking maybe we could go to the pacific ocean wait no i mean we should be more specific about which beach we want to visit this summer"},
    {"id": 9, "expect": "clean prose, preserve order number 45789",
     "raw": "the customer called and said their order number 4 5 7 8 9 hasnt arrived yet even though the tracking says it was delivered three days ago so we need to investigate what happened"},
    {"id": 10, "expect": "remove heavy fillers, clean opinion prose",
     "raw": "you know like i feel like we should um maybe reconsider the whole approach because like the current one is just not working and its causing a lot of frustration for everyone involved"},
    {"id": 11, "expect": "numbered setup steps",
     "raw": "to set up the environment you need to install python then create a virtual environment then activate it then run pip install of the requirements file and finally start the server"},
    {"id": 12, "expect": "clean prose, preserve the hearsay/ambiguity",
     "raw": "she said that he said that the project was delayed because of the the vendor issues but i heard from someone else that it was actually a budget problem so im not really sure whats going on"},
    {"id": 13, "expect": "recipe as ingredient list + method",
     "raw": "the recipe is pretty simple you take two cups of flour one cup of sugar three eggs a teaspoon of vanilla mix it all together and bake at 350 for 25 minutes"},
    {"id": 14, "expect": "bulleted list of 3 follow-ups",
     "raw": "i need to follow up on three things the contract renewal the the invoice that was disputed and the onboarding for the new hire that starts next monday"},
    {"id": 15, "expect": "problem statement + question, clean prose",
     "raw": "the the wifi keeps disconnecting every few minutes its really frustrating ive tried restarting the router and reconnecting but nothing seems to work do you have any other suggestions"},
    {"id": 16, "expect": "bulleted list of conference topics",
     "raw": "during the conference we covered a lot of topics including ai ethics data privacy the future of work and there was also a really interesting session on quantum computing"},
    {"id": 17, "expect": "casual check-in, two questions",
     "raw": "hey just wanted to quickly check in and see how youre doing with the the slides for tomorrow do you need any help and also did you get a chance to review the the budget i sent over"},
    {"id": 18, "expect": "clean technical explanation prose",
     "raw": "the the algorithm works by first sorting the array then it uses a binary search to find the target element which makes it much faster than a linear scan especially for large datasets"},
    {"id": 19, "expect": "budget breakdown; resolve self-correction 30k->15k",
     "raw": "so we have a budget of fifty thousand dollars and we need to allocate it across marketing which is about twenty thousand development thirty thousand wait no fifteen thousand and the rest for operations"},
    {"id": 20, "expect": "clean opinion prose, remove repetition/fillers",
     "raw": "i really think that um we need to to address the the elephant in the room which is that the the deadline is just not realistic given the current resources and we should push it back at least two weeks"},
]
