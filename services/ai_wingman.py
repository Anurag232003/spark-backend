"""
Spark AI Wingman Service — Personal Dating Assistant Engine.
Provides:
1. Contextual Match Icebreakers (Profile & Interests based)
2. Conversation Revivers (for stalled / dead chats)
3. AI Profile Coach & Optimization Analyzer
4. Multi-tone support (Flirty, Funny, Respectful, Casual)
5. Multi-lingual support (Hinglish, Hindi, English)
6. Dual-layer engine: Gemini API (if GEMINI_API_KEY is present) + Local Smart Context Engine fallback.
"""

import os
import random
import json
import urllib.request
from typing import List, Dict, Optional, Any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ==============================================================================
# 1. SMART CONTEXTUAL ENGINE DATA & TEMPLATES
# ==============================================================================

INTEREST_TOPIC_MAP = {
    "coffee": {
        "hinglish": {
            "flirty": [
                "Ek achhe espresso ki tarah, aapki presence mein ek rich aur rare depth hai... How do you take your coffee? ☕✨",
                "Aapka aesthetic dekh ke lagta hai you appreciate quiet specialty cafes over crowded spots... Am I right? ☕",
                "Coffee date toh bahaana hai... I'm more interested in the conversation you bring with it 😉☕",
            ],
            "funny": [
                "Ek important compatibility test: Do you actually appreciate good roast coffee, ya sugar with a drop of caffeine? 😂☕",
                "Deal karte hain: Main coffee spot decide karta hoon, and you judge my taste ruthlessly. Fair? ☕😏",
            ],
            "respectful": [
                "Good evening. Noticed your love for coffee. What's one quiet café in town where you truly enjoy spending time? ☕",
                "Hello! Always refreshing to connect with someone who appreciates a great roast. What’s your go-to brew? ☕✨",
            ],
            "casual": [
                "Slow Sunday mornings with pour-over coffee, or a quick cortado before tackling the day? ☕",
                "Specialty roast vs classic café blend... where does your palate usually lean? ☕",
            ],
            "mysterious": [
                "Coffee table books ya late night espresso conversations... aapki profile mein dono ka ek subtle balance lagta hai 🔮☕",
            ],
            "suspenseful": [
                "Maine shahar mein ek hidden café dhoonda hai jiska ambiance is unreal... but you only get the location if you pass one test ⏳☕",
            ]
        },
        "hindi": {
            "flirty": [
                "एक बेहतरीन कॉफ़ी की तरह आपके व्यक्तित्व में भी एक ख़ास कशिश और गरिमा महसूस होती है ☕✨",
                "कॉफ़ी का तो सिर्फ़ एक बहाना है, असल दिलचस्पी आपकी बातों और सोच को जानने में है 😊☕",
            ],
            "funny": [
                "एक ज़रूरी सवाल: क्या आपको वाक़ई अच्छी कॉफ़ी पसंद है या सिर्फ़ सुकून भरे कैफ़े का माहौल? 😂☕",
            ],
            "respectful": [
                "नमस्ते। आपकी प्रोफ़ाइल में कॉफ़ी के प्रति आपकी पसंद नज़र आई। आपका पसंदीदा कॉफ़ी स्पॉट कौन सा है? ☕",
            ],
            "casual": [
                "फ़ुर्सत की शाम में पसंदीदा कॉफ़ी के साथ सुकून से बैठना या दोस्तों के साथ बातचीत? ☕",
            ],
            "mysterious": [
                "आपकी पसंद में एक शांत सादगी और गहरा स्वाद नज़र आता है जो बहुत कम लोगों में मिलता है ☕🌙",
            ],
            "suspenseful": [
                "शहर में एक ऐसा कॉफ़ी कॉर्नर है जो हर किसी को नहीं पता... क्या आप उस राज़ को जानने के लिए तैयार हैं? ⏳☕",
            ]
        },
        "english": {
            "flirty": [
                "Like a perfectly pulled espresso, you have an unmistakable depth and sophistication. How do you take your coffee? ☕✨",
                "A coffee date is an easy excuse, but it's the calibre of your conversation that caught my attention 😉☕",
            ],
            "funny": [
                "Quick compatibility checkpoint: do you actually appreciate single-origin coffee, or is it 90% milk and syrups? 😂☕",
                "Deal: I pick the coffee spot, and you have full permission to critique my taste in cafes. Deal? ☕😏",
            ],
            "respectful": [
                "Good evening. Always a pleasure to connect with someone who appreciates great coffee. What's your favourite roastery? ☕✨",
                "Hello! Loved the aesthetic in your profile. What’s the one café you go to when you need to disconnect and think? ☕",
            ],
            "casual": [
                "Slow Sunday pour-overs or a quick morning Americano? What’s your daily ritual? ☕",
            ],
            "mysterious": [
                "There’s an understated quiet elegance about your coffee taste that tells me you value quality over noise 🔮☕",
            ],
            "suspenseful": [
                "I know a hidden espresso bar that feels like it belongs in Milan... but I only reveal the address on one condition ⏳☕",
            ]
        }
    },
    "travel": {
        "hinglish": {
            "flirty": [
                "You have that effortlessly worldly aura... like someone who travels for the soul rather than just postcards ✨✈️",
                "Traveling with someone tells you everything about their character. What kind of travel companion are you? 😉🗺️",
            ],
            "funny": [
                "Tell me you're not the traveler with an hourly spreadsheet itinerary... spontaneous exploration is mandatory! 😂✈️",
                "The real airport test: Are you calmly sipping an espresso at the lounge, or sprinting to the boarding gate? 😂🧳",
            ],
            "respectful": [
                "Good evening. Your travel photos reflect a genuine appreciation for culture and landscapes. What destination left the deepest mark on you? 🗺️✨",
            ],
            "casual": [
                "Secluded coastal escapes or historic old-town architecture? What recharges your mind best? 🌊🏛️",
            ],
            "mysterious": [
                "Tumhare safar ke pictures dekh ke lagta hai you search for places that have an untold story... 🔮✈️",
            ],
            "suspenseful": [
                "If we booked a one-way ticket tonight with zero planning, where would your instincts take us? ⏳✈️",
            ]
        },
        "hindi": {
            "flirty": [
                "आपकी आँखों में एक मुसाफ़िर की रूह और एक ख़ूबसूरत ठहराव दोनों नज़र आते हैं ✨✈️",
                "सफ़र तो बहुत लोग करते हैं, पर मंज़िल को महसूस करने का हुनर बहुत कम में होता है... जैसे आप में 😊",
            ],
            "funny": [
                "सफ़र में हर घंटे की प्लानिंग करते हैं या रास्ते जो मोड़ लें, वहाँ सुकून ढूंढ लेते हैं? 😂🗺️",
            ],
            "respectful": [
                "नमस्ते। आपकी यात्रा की तस्वीरें बहुत ही परिपक्व और ख़ूबसूरत हैं। किस जगह ने आपके दिल को सबसे ज़्यादा छुआ? ✈️",
            ],
            "casual": [
                "पहाड़ों का शांत सुकून या समंदर की लहरों की गहराई? आपकी रूह कहाँ ठहरती है? 🌊🏔️",
            ],
            "mysterious": [
                "आपकी प्रोफ़ाइल में एक ऐसा शांत सफ़रनामा दिखता है जो शायद हर किसी के समझ में नहीं आ सकता 🌙✈️",
            ],
            "suspenseful": [
                "अगर आपको अभी इसी वक़्त बिना किसी तैयारी के एक अनदेखे सफ़र पर निकलना पड़े, तो क्या आप तैयार हैं? ⏳✈️",
            ]
        },
        "english": {
            "flirty": [
                "You have that effortless, worldly poise that suggests you travel for perspective, not just photos ✨✈️",
                "They say you only truly know someone after traveling with them. What kind of co-traveler are you? 😉",
            ],
            "funny": [
                "Crucial test: Are you an obsessively color-coded itinerary traveler, or do you let the city guide you? 😂🗺️",
                "Lounge with a book before takeoff, or sprinting past duty-free at final call? Be honest! 😂🛫",
            ],
            "respectful": [
                "Good evening. Your travel captures reflect a quiet reverence for culture. Which journey influenced your outlook the most? 🌍✨",
            ],
            "casual": [
                "Quiet coastal retreats or dense cultural capitals? What’s your preferred headspace when you escape? 🌊🏛️",
            ],
            "mysterious": [
                "You look like someone who seeks out the places absent from the travel guides... intriguing 🔮",
            ],
            "suspenseful": [
                "If you had to pack a single carry-on right now for a spontaneous departure, where are we landing? ⏳✈️",
            ]
        }
    },
    "gym": {
        "hinglish": {
            "flirty": [
                "Physical fitness is impressive, but the mental discipline and poise behind it is what truly stands out about you 💪✨",
                "You carry yourself with unmistakable confidence and posture. Clearly that dedication pays off 😉",
            ],
            "funny": [
                "Fitness debate: Is the post-workout clarity real, or do we just convince ourselves so we survive the routine? 😂💪",
                "Tell me you balance that discipline with an unapologetic appreciation for great wine and desserts! 🍰🏋️",
            ],
            "respectful": [
                "Hello! Consistency and self-discipline always speak volumes about a person's character. Admirable dedication. 💪✨",
            ],
            "casual": [
                "How do you balance high energy training with a demanding schedule? Always curious about high-performers' routines. 🏋️",
            ],
            "mysterious": [
                "Fitness is often meditation in motion... aapki eyes mein wahi quiet focus nazar aata hai 🔮💪",
            ],
            "suspenseful": [
                "I have a challenge for our first workout or run... think you can keep pace, or should I be the one worried? ⏳😏",
            ]
        },
        "hindi": {
            "flirty": [
                "फ़िटनेस का अनुशासन अपनी जगह है, पर आपकी गरिमा और सादगी सबसे ज़्यादा दिल जीतती है ✨💪",
            ],
            "funny": [
                "वर्कआउट का अनुशासन कमाल है, पर क्या कभी दिल खोलकर पसंदीदा खाने का लुत्फ़ भी उठाते हैं? 😂🍰",
            ],
            "respectful": [
                "नमस्ते। सेहत और अनुशासन के प्रति आपका समर्पण वाक़ई तारीफ़ के क़ाबिल है। 💪✨",
            ],
            "casual": [
                "व्यस्त दिनचर्या के बीच ख़ुद को फ़िट और ऊर्जावान रखने का आपका क्या राज़ है? 🏋️",
            ],
            "mysterious": [
                "शारीरिक शक्ति से कहीं ज़्यादा आपका मानसिक संयम आपकी प्रोफ़ाइल में साफ़ झलकता है 🌙💪",
            ],
            "suspenseful": [
                "अनुशासन में तो आप अव्वल हैं... क्या ज़िंदगी के रोमांचक मोड़ों पर भी इतना ही भरोसा रखते हैं? ⏳",
            ]
        },
        "english": {
            "flirty": [
                "Physical fitness is admirable, but it’s the quiet mental composure behind it that truly commands attention 💪✨",
                "You hold yourself with the unmistakable posture of someone who commands their own discipline 😉",
            ],
            "funny": [
                "Tell me you balance the high-performance gym lifestyle with an unapologetic appreciation for good wine and pasta! 😂🍝",
            ],
            "respectful": [
                "Good evening. Consistency in wellness speaks deeply to character and self-respect. Commendable work. 💪✨",
            ],
            "casual": [
                "How do you usually balance high-intensity fitness with the demands of work and life? 🏋️",
            ],
            "mysterious": [
                "There is a focused calm in your eyes that usually belongs to people who push their limits daily 🔮",
            ],
            "suspenseful": [
                "I have a subtle bet on who holds stronger stamina—care to test it on a sunrise run? ⏳😏",
            ]
        }
    },
    "foodie": {
        "hinglish": {
            "flirty": [
                "Great dining is an art, but exceptional company turns it into an unforgettable experience. What's your ideal dinner evening? 🍷✨",
                "Aapki profile dekh ke lagta hai you have refined taste. I'd love to introduce you to a quiet hidden bistro I know 😉🍽️",
            ],
            "funny": [
                "We can disagree on philosophy, but if you're the type who orders the safe option at every restaurant, we might have words! 😂🍷",
                "Fine dining tasting menu with great wine, or an unpretentious hole-in-the-wall with unmatched flavors? 🍝",
            ],
            "respectful": [
                "Good evening. It’s always wonderful to connect with someone who appreciates genuine culinary craft. What cuisine fascinates you most? 🍽️✨",
            ],
            "casual": [
                "Cooking an elaborate meal at home with jazz playing, or discovering an intimate new restaurant? What's your pace? 🍷🕯️",
            ],
            "mysterious": [
                "Taste in food usually reflects how someone experiences life... aapka taste kaafi nuanced lagta hai 🔮🍽️",
            ],
            "suspenseful": [
                "I know a hidden supper club that serves the most remarkable flavours in the city... condition yeh hai ki menu secret rahega ⏳🍷",
            ]
        },
        "hindi": {
            "flirty": [
                "ज़ायके की परख अपनी जगह है, पर एक ख़ूबसूरत शाम में अच्छी सोहबत का कोई मुक़ाबला नहीं 🍷✨",
            ],
            "funny": [
                "क्या आप भी उन लोगों में से हैं जो नया मेन्यू देखकर भी वही अपना पुराना पसंदीदा डिश ऑर्डर करते हैं? 😂🍝",
            ],
            "respectful": [
                "नमस्ते। बेहतरीन भोजन और ज़ायके की समझ होना अपने आप में एक कला है। आपका पसंदीदा व्यंजन कौन सा है? 🍽️",
            ],
            "casual": [
                "घर पर सुकून से कुछ ख़ास पकाना या शहर के किसी उम्दा रेस्तराँ में शाम बिताना? 🍷",
            ],
            "mysterious": [
                "स्वाद की समझ आपके जीवन के प्रति गहरे दृष्टिकोण को दर्शाती है... बहुत प्रभावित करने वाली प्रोफ़ाइल है 🌙",
            ],
            "suspenseful": [
                "अगर मैं आपको एक ऐसा डिनर ऑफर करूँ जिसका मेन्यू पूरी तरह एक सरप्राइज़ हो, तो क्या आप तैयार हैं? ⏳🍽️",
            ]
        },
        "english": {
            "flirty": [
                "Fine food is an art, but extraordinary company turns it into an experience. What does an exceptional evening look like to you? 🍷✨",
                "You strike me as someone with discerning taste. I know an intimate little spot you'd thoroughly appreciate 😉",
            ],
            "funny": [
                "We can agree on almost anything, but ordering the safest chicken dish at a specialized restaurant is where I draw the line! 😂🍷",
            ],
            "respectful": [
                "Good evening. Always a pleasure connecting with someone who appreciates the nuance of culinary craft. What cuisine inspires you? 🍽️✨",
            ],
            "casual": [
                "Unwinding with an artisanal home-cooked meal, or exploring a new corner bistro on a Friday night? 🍷",
            ],
            "mysterious": [
                "Palate often mirrors emotional range... yours seems wonderfully sophisticated 🔮",
            ],
            "suspenseful": [
                "I have a reservation at an undisclosed speakeasy this weekend... care to join for the reveal? ⏳🍸",
            ]
        }
    },
    "movies": {
        "hinglish": {
            "flirty": [
                "Cinema taste tells you everything about someone's emotional depth. What's one film that genuinely stayed with you? 🎬✨",
                "A vintage film screening, quiet conversation, and great wine... sounds like an evening with high potential 😉🎞️",
            ],
            "funny": [
                "Movie pact: If we watch a psychological thriller, we have to spend at least 30 minutes debating the motives over drinks! 🎬🍷",
            ],
            "respectful": [
                "Good evening. Cinema that moves us often reveals our inner values. What film has shaped your perspective most? 🎬✨",
            ],
            "casual": [
                "Classic slow-burn dramas or edge-of-the-seat psychological thrillers? Where does your taste gravitate? 🎞️",
            ],
            "mysterious": [
                "You have that cinematic stillness in your photos... like a character with an unrevealed back-story 🔮🎬",
            ],
            "suspenseful": [
                "Tell me the twist in your favourite movie without naming the movie... let's see if I can deduce it ⏳🎥",
            ]
        },
        "hindi": {
            "flirty": [
                "सिनेमा की समझ इंसान की संवेदनशीलता को बयाँ करती है... आपकी पसंद में वही गहराई झलकती है 🎬✨",
            ],
            "funny": [
                "फ़िल्म ख़त्म होने के बाद क्या आप भी उसके किरदारों और अंत पर घंटों बहस करने वालों में से हैं? 😂🎬",
            ],
            "respectful": [
                "नमस्ते। आपकी प्रोफ़ाइल में सिनेमा के प्रति आपकी समझ अच्छी लगी। कौन सी ऐसी फ़िल्म है जो दिल के सबसे क़रीब है? 🎥",
            ],
            "casual": [
                "सार्थक सिनेमा या क्लासिक रेट्रो कहानियाँ? आपका मूड किस तरफ़ रहता है? 🎬",
            ],
            "mysterious": [
                "आपकी तस्वीरों में एक ऐसा सिनेमाई ठहराव है जो बरबस ध्यान अपनी ओर खींच लेता है 🌙🎞️",
            ],
            "suspenseful": [
                "अगर हमारी इस मुलाक़ात की एक पटकथा लिखी जाए, तो अगला दृश्य क्या होना चाहिए? ⏳🎬",
            ]
        },
        "english": {
            "flirty": [
                "Taste in cinema is a direct window into emotional intelligence. What’s one film that permanently altered your worldview? 🎬✨",
                "A private screening, thoughtful conversation, and a good vintage... sounds like a well-spent evening 😉🎞️",
            ],
            "funny": [
                "A non-negotiable condition: If we watch a thriller together, we dissect the protagonist's psychology for an hour afterward! 😂🎬",
            ],
            "respectful": [
                "Good evening. Great storytelling leaves an enduring impression. What cinematic work has stayed with you the longest? 🎬✨",
            ],
            "casual": [
                "Slow-burn neo-noirs or character-driven independent dramas? What holds your attention best? 🎞️",
            ],
            "mysterious": [
                "There is an evocative, cinematic poise in how you carry yourself... quite captivating 🔮",
            ],
            "suspenseful": [
                "Describe the turning point in your life as if it were a film climax... I'm listening ⏳🎥",
            ]
        }
    },
    "music": {
        "hinglish": {
            "flirty": [
                "Music is an intimate reflection of the soul. Send me one track that best captures your headspace right now 🎧✨",
                "Aapka music taste reflects a certain depth and elegance... it immediately made me stop and listen 🎶",
            ],
            "funny": [
                "Does your playlist transition gracefully from vintage soulful classics straight into intense late-night beats? 😂🎧",
            ],
            "respectful": [
                "Good evening. Music often mirrors a person’s inner cadence. What artist or composer has been your anchor lately? 🎵✨",
            ],
            "casual": [
                "Live acoustic sets in a dimly lit lounge, or vinyl records on a quiet night in? 🎸🕯️",
            ],
            "mysterious": [
                "The melodies we return to in private reveal who we truly are... what does your secret playlist sound like? 🔮🎶",
            ],
            "suspenseful": [
                "Pick one song that sets the exact mood for our first meeting... choose carefully ⏳🎧",
            ]
        },
        "hindi": {
            "flirty": [
                "संगीत की समझ और आपकी सादगी... दोनों में एक ऐसा सुर है जो दिल को सुकून पहुँचाता है 🎵✨",
            ],
            "funny": [
                "क्या आपकी प्लेलिस्ट में भी ग़ज़लों से लेकर रॉक म्यूज़िक तक का अप्रत्याशित मेल है? 😂🎧",
            ],
            "respectful": [
                "नमस्ते। संगीत इंसान के जज़्बातों का आईना होता है। किस धुन या गीत से आपको सबसे गहरा लगाव है? 🎶",
            ],
            "casual": [
                "धीमी आवाज़ में बजता सूफ़ी संगीत या पुराने सदाबहार नग़मे? शाम को क्या सुनना पसंद करते हैं? 🎧",
            ],
            "mysterious": [
                "आपकी ख़ामोशी में भी एक ख़ूबसूरत संगीत महसूस होता है... बहुत शालीन व्यक्तित्व है आपका 🌙🎵",
            ],
            "suspenseful": [
                "एक ऐसा गीत बताइए जो आपके किसी अनकहे जज़्बात को बयाँ करता हो... ⏳🎶",
            ]
        },
        "english": {
            "flirty": [
                "A person's playlist is their most honest confession. Share the one song that speaks closest to your mood tonight 🎧✨",
                "There’s an undeniable sophistication in the music you lean into. It caught my attention instantly 🎶",
            ],
            "funny": [
                "Tell me your musical taste has the maturity to appreciate classic vinyl and the audacity to enjoy guilty pleasures! 😂🎧",
            ],
            "respectful": [
                "Good evening. Musical taste often reflects one’s emotional depth. Who is an artist you never grow weary of? 🎵✨",
            ],
            "casual": [
                "Intimate acoustic sessions in a quiet lounge, or vinyl spinning while you unwind at home? 🎸🕯️",
            ],
            "mysterious": [
                "What melody plays in the background when the rest of the world goes quiet? 🔮🎶",
            ],
            "suspenseful": [
                "Send me the one track you wouldn't play for just anyone... let's see what it reveals ⏳🎧",
            ]
        }
    },
    "pets": {
        "hinglish": {
            "flirty": [
                "People with quiet empathy towards animals naturally possess a rare warmth... like you 🐾✨",
            ],
            "funny": [
                "Important protocol: If your pet judges me upon arrival, do I get a second appeal or instant disqualification? 😂🐾",
            ],
            "respectful": [
                "Good evening. The way someone treats their animals always speaks volumes about their integrity and heart. 🐾✨",
            ],
            "casual": [
                "How does your pet react to new people—instant loyalty or discerning observation? 🐕🐈",
            ],
            "mysterious": [
                "Animals have an instinct for genuine energy... I suspect yours is exceptionally loyal to you 🔮🐾",
            ],
            "suspenseful": [
                "Passing the pet inspection might be the highest-stakes exam of this match... accept the challenge? ⏳🐾",
            ]
        },
        "hindi": {
            "flirty": [
                "मासूम बेज़ुबानों से लगाव रखने वाले लोगों के दिल में एक ख़ास नज़ाकत और हमदर्दी होती है... जैसे आप में 🐾✨",
            ],
            "funny": [
                "अगर आपके पेट ने मुझे पहली नज़र में मंज़ूर नहीं किया, तो क्या दूसरा मौक़ा मिलेगा? 😂🐕",
            ],
            "respectful": [
                "नमस्ते। बेज़ुबानों के प्रति आपकी दयालुता और प्यार आपके साफ़ दिल की गवाही देता है। 🐾✨",
            ],
            "casual": [
                "घर में पेट्स की मौजूदगी पूरे माहौल में एक सुकून भर देती है। आपका उनके साथ दिन कैसा बीतता है? 🐾",
            ],
            "mysterious": [
                "जानवर साफ़ रूह को तुरंत पहचान लेते हैं... आपकी प्रोफ़ाइल में वही सुकून नज़र आता है 🌙🐾",
            ],
            "suspenseful": [
                "क्या आपका पेट नए लोगों को आसानी से अपनाता है या उसका भरोसा जीतना एक इम्तिहान है? ⏳🐾",
            ]
        },
        "english": {
            "flirty": [
                "Gentle compassion toward animals is one of the most attractive traits a person can carry. You have it effortlessly 🐾✨",
            ],
            "funny": [
                "Does your pet conduct a formal interview, or can I win them over with proper decorum and treats? 😂🐾",
            ],
            "respectful": [
                "Good evening. How someone nurtures their companions reveals genuine character. Beautiful bond you share. 🐾✨",
            ],
            "casual": [
                "Discerning judge of character or immediate best friend? What’s your pet’s temperament? 🐕🐈",
            ],
            "mysterious": [
                "Animals instinctively gravitate toward grounded souls. It makes complete sense in your case 🔮🐾",
            ],
            "suspenseful": [
                "Winning your approval is step one; surviving your pet's scrutiny is the real final boss ⏳🐾",
            ]
        }
    },
    "gaming": {
        "hinglish": {
            "flirty": [
                "Strategic intellect is attractive... do you play to win, or play for the art of the challenge? 😉🎮",
            ],
            "funny": [
                "In competitive situations, are you calmly analytical, or does the competitive streak take over entirely? 😂🎮",
            ],
            "respectful": [
                "Good evening. Interactive storytelling and complex game design are true modern art forms. What narrative moved you most? 🎮✨",
            ],
            "casual": [
                "Immersive story campaigns that demand focus, or high-strategy co-op sessions? 🕹️",
            ],
            "mysterious": [
                "Strategy in complex games often mirrors how a person makes decisions in life... fascinating 🔮🎮",
            ],
            "suspenseful": [
                "1v1 match where the loser buys dinner at the winner's choice of venue. Do you take the wager? ⏳🎮",
            ]
        },
        "hindi": {
            "flirty": [
                "खेल में रणनीति और ज़िंदगी में गरिमा... दोनों का तालमेल बहुत कम लोगों में मिलता है 🎮✨",
            ],
            "funny": [
                "हारने पर शांत मुसकुराहट या फिर अंदर ही अंदर अगली बाज़ी जीतने की ज़िद? सच बताइएगा! 😂🎮",
            ],
            "respectful": [
                "नमस्ते। खेलों में गहरी सोच और धैर्य दोनों की ज़रूरत होती है। आपका सबसे पसंदीदा खेल कौन सा है? 🎮",
            ],
            "casual": [
                "कहानियों पर आधारित गहरे खेल या त्वरित रणनीति वाले? आपकी प्राथमिकता क्या है? 🕹️",
            ],
            "mysterious": [
                "हर चाल के पीछे एक सोची-समझी रणनीति... आपकी प्रोफ़ाइल में एक शांत गहराई है 🌙🎮",
            ],
            "suspenseful": [
                "एक दोस्ताना मुक़ाबला, और हारने वाले को बेहतरीन डिनर होस्ट करना होगा... क्या आप चुनौती स्वीकार करते हैं? ⏳🎮",
            ]
        },
        "english": {
            "flirty": [
                "Strategic minds are inherently captivating. Do you approach life with the same sharp instincts you bring to a game? 😉🎮",
            ],
            "funny": [
                "When the stakes get high, are you coolly composed or does an unapologetic competitive streak emerge? 😂🎮",
            ],
            "respectful": [
                "Good evening. Interactive design and expansive worlds are magnificent creative achievements. What title holds your highest esteem? 🎮✨",
            ],
            "casual": [
                "Expansive narrative-driven journeys or intricate tactical simulations? Where does your downtime go? 🕹️",
            ],
            "mysterious": [
                "How someone navigates complex puzzles often exposes their psychological patience... intriguing 🔮",
            ],
            "suspenseful": [
                "A friendly wager: one game, victor chooses the setting for our first evening. Are you confident enough to accept? ⏳🎮",
            ]
        }
    }
}

# ==============================================================================
# GENERAL OPENERS (MATURE MEN & WOMEN STANDARDS)
# ==============================================================================

GENERAL_OPENERS = {
    "hinglish": {
        "mysterious": [
            "Tumhari presence mein ek quiet confidence aur subtle depth notice hoti hai jo kaafi rare hai... I had to say hello.",
            "Aapki profile dekh ke lagta hai you have some incredible stories that only a select few get to hear... Am I right?",
            "There’s an intriguing elegance about you jo easily crowd se alag stand out karti hai... What inspired that look?",
            "Tumhari vibe se lagta hai you know exactly what you want out of life... rare quality in people these days.",
        ],
        "suspenseful": [
            "Maine tumhari profile mein ek bohot subtle detail notice ki jo almost sabhi miss kar dete hain... Care to know?",
            "Ek candid sawal poochna tha... depending on your answer, yeh conversation kaafi interesting hone wali hai.",
            "Aapka aesthetic dekh ke lagta hai you're either an effortless minimalist ya master of subtle chaos... which one is it?",
            "Between your taste and your smile, you clearly have high standards. Let's see if our conversation meets them.",
        ],
        "flirty": [
            "They say elegance is about being remembered, not noticed. Safe to say, you left an impression ✨",
            "Aapki smile mein ek effortless warmth hai jo instant attention grab karti hai... How has your evening been?",
            "Right swipe karna toh inevitable tha, but your vibe genuinely made me stop and appreciate. Good evening ✨",
            "Ek rare combination notice kiya: ambition with an effortlessly graceful charm. Truly captivating.",
        ],
        "funny": [
            "Are we going to pretend we didn't both swipe right because of impeccable taste, or skip straight to the good banter?",
            "Deal karte hain: no boring small talk about the weather, just unfiltered opinions on what actually makes life exciting.",
            "Tell me you're not the type who agrees on a dinner spot and then changes their mind 3 minutes before arriving...",
            "Rule number one of connecting: do I need to prepare a 5-star itinerary or just great conversation and quality coffee?",
        ],
        "respectful": [
            "Good evening. It’s genuinely refreshing to see someone articulate their passions with such clarity. How has your week been?",
            "Hello. Your profile reflects a wonderful sense of balance, ambition, and grace. Hope your day has treated you well.",
            "Namaste. Very rarely do you find a profile with such authentic depth and poise. Lovely connecting with you.",
            "Hi! Loved the thoughtful aesthetic and perspective you share. What’s been the most fulfilling part of your week?",
        ],
        "casual": [
            "Quiet evenings with great wine and music, or lively rooftop conversations? Where does your ideal unwind begin?",
            "How do you usually transition from a demanding work week into weekend mode? Any go-to spots around the city?",
            "Simple question to start: what’s one passion or project that's been keeping you genuinely excited lately?",
            "Unwinding with a good book and coffee, or spontaneous city strolls? What suits your rhythm?",
        ]
    },
    "hindi": {
        "mysterious": [
            "आपकी सादगी में एक अनकही गहराई और शालीनता है जो बहुत कम देखने को मिलती है...",
            "आपकी प्रोफ़ाइल देखकर लगता है कि आपके पास ज़िंदगी के कुछ ऐसे ख़ूबसूरत क़िस्से हैं जो हर किसी के हिस्से नहीं आते।",
            "एक शांत आत्मविश्वास जो बिना कुछ कहे भी बहुत कुछ बयाँ कर देता है... आपसे मिलकर अच्छा लगा।",
        ],
        "suspenseful": [
            "आपकी प्रोफ़ाइल में एक ऐसी बात नज़र आई जिसने मेरी राय को पूरी तरह बदल दिया... बताऊँ क्या?",
            "आपसे एक बेबाक सवाल पूछना था... बस वादा कीजिए कि जवाब बिल्कुल सच्चा होगा?",
            "आपकी पसंद और अंदाज़ देखकर लगता है कि आपको साधारणीकरण बिल्कुल पसंद नहीं। क्या मैं सही हूँ?",
        ],
        "flirty": [
            "कहते हैं ख़ूबसूरती ध्यान खींचती है, पर शालीनता दिल जीत लेती है... आपकी प्रोफ़ाइल में दोनों हैं ✨",
            "आपकी मुस्कान में एक सहज गरिमा है जो बहुत दिलकश लगती है। कैसी गुज़र रही है आपकी शाम?",
            "कुछ चेहरों में एक ऐसा ठहराव होता है जो भीड़ से अलग खड़ा कर देता है... आपसे परिचय होना सुखद है।",
        ],
        "funny": [
            "एक वादा करते हैं: मौसम की बोरिंग बातें छोड़ते हैं और सीधी दिलचस्प बातों पर आते हैं! क्या ख़्याल है?",
            "सच बताइए, क्या आप भी उनमें से हैं जो डिनर की जगह तय होने के बाद आख़िरी 5 मिनट में मूड बदल लेते हैं? 😂",
            "हमारी पसंद बेहतरीन है तभी तो हम दोनों का मैच हुआ... अब देखना यह है कि बातचीत में कौन बाज़ी मारता है!",
        ],
        "respectful": [
            "नमस्ते। आपकी प्रोफ़ाइल में एक बहुत ही सुलझा हुआ और गरिमामय व्यक्तित्व झलकता है। आपका दिन कैसा बीता?",
            "हेलो। आपका प्रोफ़ाइल पढ़कर अच्छा लगा। आज कल किस काम या शौक़ में मन लग रहा है?",
            "प्रणाम। साफ़गोई और सादगी आज के दौर में दुर्लभ हैं, जो आपकी बातों में साफ़ नज़र आती हैं।",
        ],
        "casual": [
            "वीकेंड पर पसंदीदा कॉफ़ी के साथ सुकून की शाम, या शहर की किसी ख़ास जगह पर सैर? आपकी पसंद क्या है?",
            "व्यस्त दिनचर्या के बाद ख़ुद को रिलैक्स करने का आपका सबसे पसंदीदा तरीक़ा क्या है?",
            "कामकाज के बीच ख़ुद के लिए वक़्त निकालना कितना आसान या मुश्किल हो पाता है आपके लिए?",
        ]
    },
    "english": {
        "mysterious": [
            "You carry yourself with the kind of quiet poise that suggests you have a fascinating story. Care to share a chapter?",
            "Most people probably notice your looks first, but there's a subtle depth in your presence that feels much more compelling.",
            "There’s an intriguing calm about your energy—rarely found, impossible to overlook.",
            "You strike me as someone who observes everything and reveals very little. What's caught your attention today?",
        ],
        "suspenseful": [
            "I noticed a subtle nuance in your profile that made me question my entire first impression of you... Want to hear it?",
            "I have one honest question, and depending on how you answer, this is either going to be very brief or dangerously interesting.",
            "Between your taste and your aesthetic, you clearly don't settle for the ordinary. Let's test our chemistry.",
        ],
        "flirty": [
            "They say elegance is about being remembered, not just noticed. You definitely made a lasting impression ✨",
            "A rare blend of effortless grace and unmistakable ambition. I couldn't scroll past without introducing myself.",
            "I usually don't reach out first, but your vibe carries a magnetic confidence that was impossible to ignore 😉",
        ],
        "funny": [
            "Are we going to pretend we didn't both match because of impeccable taste, or dive straight into proper banter?",
            "A quick agreement before we start: zero small talk about the weather, just honest opinions on what makes life exciting.",
            "Do I need to prepare a curated 5-course itinerary, or do you appreciate spontaneous hole-in-the-wall discoveries? 😂",
        ],
        "respectful": [
            "Good evening. It’s genuinely refreshing to encounter someone with such thoughtful depth and poise on here. How's your week unfolding?",
            "Hello. Your profile reflects a great sense of intent and individuality. What’s something that genuinely inspired you recently?",
            "Hi there. Appreciate the calm, grounded energy in your photos. Hope you’re having a productive and fulfilling day.",
        ],
        "casual": [
            "Unwinding with a vintage playlist and good conversation, or exploring vibrant dinner spots? Where's your comfort zone?",
            "What's the one passion or creative outlet that keeps your energy recharged after a hectic week?",
            "How do you typically disconnect from the noise of the city when the weekend arrives?",
        ]
    }
}

# ==============================================================================
# CONVERSATION REVIVER SUGGESTIONS (MATURE MEN & WOMEN RE-ENGAGEMENT)
# ==============================================================================

REVIVE_SUGGESTIONS = {
    "hinglish": {
        "mysterious": [
            "Silence hamesha sabse bada statement hota hai... par tumhari silence mein ek intriguing story lag rahi hai.",
            "Kuch conversations adhoori reh jaati hain, but I had an intuitive feeling this wasn't supposed to be one of them.",
            "Tumhari quiet energy notice ki... saving your best thoughts for a quiet evening or just naturally selective?",
        ],
        "suspenseful": [
            "Humari conversation ek fascinating point pe pause ho gayi thi... care to pick up where we left off, ya plot twist ka wait karein?",
            "I had an interesting observation about how our conversation paused... want to hear my hypothesis?",
            "Are you testing my patience with this cliffhanger, or did life genuinely throw you into a whirlwind?",
        ],
        "flirty": [
            "I usually don't double text, but letting a conversation this promising fade out felt like a poor executive decision 😉",
            "Aapki presence yaad aayi... hope life is treating you with the same grace you carry.",
            "Assuming life got pleasantly busy on your end... but I wanted to make sure our spark didn't go unattended ✨",
        ],
        "funny": [
            "Did work swallow you whole, or are you just selectively social? (No judgment either way, I respect the boundary 😉)",
            "Assuming you’re currently plotting world domination. Take your time, but drop a sign when you're back.",
            "I'll give you the benefit of the doubt: either a high-stakes deadline or an intense Netflix binge took over! 😂",
        ],
        "respectful": [
            "Good evening. Knowing how demanding schedules can get, no pressure at all—just wanted to see how your week is shaping up.",
            "Hello. Saw something today that brought our conversation to mind. Hope work and life have been kind to you.",
            "Hey! Hope you're managing to take a well-deserved breather amidst the daily hustle.",
        ],
        "casual": [
            "Just checking in—hope the week hasn't been too overwhelming. How's life on your side?",
            "Reviving this because good conversations are hard to come by. How's everything going with you?",
            "Weekend prep mode or caught in the mid-week rush? Hope all is well.",
        ]
    },
    "hindi": {
        "mysterious": [
            "ख़ामोशी भी अपनी जगह ख़ूबसूरत है... पर आपकी ख़ामोशी में कोई गहरा राज़ महसूस होता है।",
            "कुछ बातें अनकही रह जाएँ तो अधूरी लगती हैं... सोचा एक बार हालचाल पूछ लूँ।",
            "शायद आप अपने ख़यालों में व्यस्त हैं... पर इस बातचीत में एक ख़ास ठहराव था जो याद आया।",
        ],
        "suspenseful": [
            "हमारी बातचीत एक बहुत दिलचस्प मोड़ पर आकर रुक गई... क्या कहानी आगे बढ़ाने का इरादा है?",
            "एक छोटा सा सवाल मन में था... क्या आप जान-बूझकर इंतज़ार करा रहे हैं या वाक़ई वक़्त नहीं मिला?",
        ],
        "flirty": [
            "व्यस्त दिनचर्या में भी कुछ लोगों का ख़्याल बरबस आ ही जाता है... उम्मीद है आपका दिन सुकून भरा रहा ✨",
            "बातचीत थोड़ी थम गई है, पर आपकी बातों का असर अभी भी बरक़रार है 😊",
        ],
        "funny": [
            "लगता है ऑफ़िस के काम ने आपको पूरी तरह घेर रखा है! जब भी फ़ुर्सत मिले, एक छोटा सा हेलो भेजिएगा।",
            "ख़ामोशी इतनी लंबी हो गई कि लगा कहीं आप किसी गुप्त मिशन पर तो नहीं निकल गए? 😂",
        ],
        "respectful": [
            "नमस्ते। कोई जल्दबाज़ी नहीं, बस यह जानने के लिए संदेश भेजा कि आपका हफ़्ता कैसा बीत रहा है।",
            "उम्मीद है कि काम के बीच आपको ख़ुद के लिए भी थोड़ा वक़्त मिल पा रहा होगा।",
        ],
        "casual": [
            "बस यह देखने के लिए मैसेज किया कि सब कुछ ठीक-ठाक चल रहा है या नहीं। आपका दिन कैसा रहा?",
            "उम्मीद है कि सप्ताह का यह हिस्सा आपके लिए हल्का और सुकून देने वाला साबित हो रहा होगा।",
        ]
    },
    "english": {
        "mysterious": [
            "Silence in an age of non-stop notifications is almost admirable. What's been occupying your world lately?",
            "I'd like to think you're simply saving your best conversation for a quiet evening over drinks...",
            "Some connections are meant to pause and pick right back up with more depth. Hope all is well.",
        ],
        "suspenseful": [
            "Leaving this conversation on an unresolved cliffhanger feels almost criminal. Care to resolve it?",
            "I had an intriguing hypothesis about why our chat went quiet... care to confirm or deny?",
        ],
        "flirty": [
            "I rarely circle back on stalled chats, but I have an intuition that our conversation had much more to offer 😉",
            "Assuming you got swept up in something captivating... hope you're leaving a little room for good banter ✨",
        ],
        "funny": [
            "Did work completely consume your calendar, or are you just testing my conversational stamina? 😉",
            "Assuming you’re either closing a high-stakes deal or lost in thought. Either way, say hello when you surface.",
        ],
        "respectful": [
            "Good evening. Just checking in with zero expectations—hope you're navigating a busy week with ease.",
            "Hello. Ran into something that reminded me of our chat. Hope everything in your world is progressing smoothly.",
        ],
        "casual": [
            "Checking in to see if you survived the week in one piece. How are things unfolding on your end?",
            "No pressure to reply right away—just bringing a little momentum back to our chat.",
        ]
    }
}


# ==============================================================================
# 2. GEMINI LLM CALLER (OPTIONAL HIGH-IQ AI LAYER)
# ==============================================================================

async def call_gemini_llm(prompt: str) -> Optional[str]:
    """
    Invokes Google Gemini via REST using GEMINI_API_KEY.
    Tries gemini-flash-lite-latest first, falls back to gemini-flash-latest.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if not api_key:
        return None

    models_to_try = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 300,
            "topP": 0.95
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return text.strip()
        except Exception as e:
            print(f"[AI_WINGMAN] Gemini {model_name} attempt skipped/failed: {e}")
            continue

    return None


# ==============================================================================
# 3. CORE PUBLIC SERVICES
# ==============================================================================

def normalize_interest(interest: str) -> str:
    """Strips emojis and converts to lowercase keyword."""
    s = interest.lower()
    for key in INTEREST_TOPIC_MAP:
        if key in s:
            return key
    return s.strip()

def extract_matched_topics(match_profile: Dict[str, Any]) -> List[str]:
    """Finds key topics like coffee, travel, pets, gym from match's profile."""
    topics = set()
    interests = match_profile.get("interests", []) or []
    for item in interests:
        norm = normalize_interest(str(item))
        if norm in INTEREST_TOPIC_MAP:
            topics.add(norm)

    bio = (match_profile.get("bio") or "").lower()
    for key in INTEREST_TOPIC_MAP:
        if key in bio:
            topics.add(key)

    prompts = match_profile.get("prompts", []) or []
    for p in prompts:
        ans = (p.get("answer") or "").lower()
        for key in INTEREST_TOPIC_MAP:
            if key in ans:
                topics.add(key)

    return list(topics)


VALID_TONES = ["mysterious", "suspenseful", "flirty", "funny", "respectful", "casual"]

TONE_DESCRIPTIONS = {
    "mysterious": "Deeply intriguing, enigmatic, and magnetic. Create an alluring curiosity gap with understated psychological depth. Mature, quiet confidence.",
    "suspenseful": "High-stakes adult curiosity, daring observation or compelling dilemma that commands an immediate, engaged reply.",
    "flirty": "Sensual charm, understated romantic tension, sophisticated chemistry between two mature adults.",
    "funny": "Dry wit, sharp observational humor, playful adult banter without slapstick or juvenile silliness.",
    "respectful": "High-value gentleman or lady approach — articulate, appreciative of depth, culture, and character.",
    "casual": "Effortless, relaxed, unbothered confidence with genuine curiosity."
}

async def generate_icebreakers(
    match_profile: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]] = None,
    tone: str = "mysterious",
    language: str = "hinglish"
) -> Dict[str, Any]:
    """
    Generates 3-4 creative opening lines based on match's profile, interests, and bio.
    tone: 'mysterious' | 'suspenseful' | 'flirty' | 'funny' | 'respectful' | 'casual'
    language: 'hinglish' | 'hindi' | 'english'
    """
    tone = tone.lower() if tone in VALID_TONES else "mysterious"
    language = language.lower() if language in ["hinglish", "hindi", "english"] else "hinglish"

    match_name = match_profile.get("name", "Match")
    matched_topics = extract_matched_topics(match_profile)

    # 1. Try Gemini LLM if key is available
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if api_key:
        tone_instruction = TONE_DESCRIPTIONS.get(tone, "")
        prompt = (
            f"You are Spark AI Wingman — the world's most sophisticated, charismatic, and emotionally intelligent dating advisor.\n"
            f"Generate 3 magnetic, mature, high-value opening lines for a dating app conversation.\n"
            f"Target Match: {match_name}\n"
            f"Bio: {match_profile.get('bio', '')}\n"
            f"Interests: {match_profile.get('interests', [])}\n"
            f"Tone: {tone.upper()} ({tone_instruction})\n"
            f"Language: {language}\n"
            f"STRICT ADULT MATURITY STANDARDS (MEN & WOMEN LEVEL):\n"
            f"1. ADULT POISE: Write from the perspective of an emotionally intelligent, high-value, mature MAN or WOMAN in their late 20s or 30s. NEVER sound like a juvenile teenager, boy, or girl.\n"
            f"2. ZERO CHILDISH CLICHÉS: Strictly NO cheesy pickup lines, NO cartoonish tropes (no aliens, astronauts, kidnappers, zombies, Hogwarts, momos/panipuri silliness).\n"
            f"3. SOPHISTICATED ATTRACTION: Use effortless charm, subtle romantic tension, intellectual curiosity, elegant banter, and emotional intelligence.\n"
            f"4. NATURAL DIALOGUE: In Hinglish or Hindi, use natural, mature, tasteful conversational vocabulary that an attractive, worldly adult uses.\n"
            f"5. Output strictly a valid JSON array of 3 strings: [\"line 1\", \"line 2\", \"line 3\"]. No markdown or intro text."
        )
        llm_resp = await call_gemini_llm(prompt)
        if llm_resp:
            try:
                clean_json = llm_resp
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0]
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0]
                parsed = json.loads(clean_json.strip())
                if isinstance(parsed, list) and len(parsed) >= 2:
                    return {
                        "suggestions": parsed[:4],
                        "matchedTopics": matched_topics,
                        "tone": tone,
                        "language": language,
                        "engine": "gemini-ai"
                    }
            except Exception:
                pass

    # 2. Local Smart Contextual Fallback Engine
    suggestions: List[str] = []

    # First add topic-specific openers if topics exist
    for topic in matched_topics:
        topic_dict = INTEREST_TOPIC_MAP.get(topic, {}).get(language, {}).get(tone, [])
        if topic_dict:
            suggestions.extend(random.sample(topic_dict, min(len(topic_dict), 2)))

    # Fill remaining from general openers
    general_pool = GENERAL_OPENERS.get(language, {}).get(tone, GENERAL_OPENERS["hinglish"]["mysterious"])
    available_general = [s for s in general_pool if s not in suggestions]
    random.shuffle(available_general)

    needed = 4 - len(suggestions)
    if needed > 0:
        suggestions.extend(available_general[:needed])

    # If still under 3, pull from fallback
    if len(suggestions) < 3:
        backup = GENERAL_OPENERS["hinglish"]["mysterious"]
        for b in backup:
            if b not in suggestions:
                suggestions.append(b)
            if len(suggestions) >= 3:
                break

    return {
        "suggestions": suggestions[:4],
        "matchedTopics": matched_topics,
        "tone": tone,
        "language": language,
        "engine": "smart-context"
    }


async def generate_chat_revivers(
    recent_messages: List[Dict[str, Any]],
    match_profile: Dict[str, Any],
    tone: str = "mysterious",
    language: str = "hinglish"
) -> Dict[str, Any]:
    """
    Generates follow-up lines when chat has stalled or went quiet.
    """
    tone = tone.lower() if tone in VALID_TONES else "mysterious"
    language = language.lower() if language in ["hinglish", "hindi", "english"] else "hinglish"

    match_name = match_profile.get("name", "Match")

    # 1. Try Gemini LLM if key is available
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if api_key:
        last_msgs_text = "\n".join([f"{m.get('sender', 'user')}: {m.get('text', '')}" for m in recent_messages[-3:]])
        tone_instruction = TONE_DESCRIPTIONS.get(tone, "")
        prompt = (
            f"You are Spark AI Wingman — the world's most sophisticated, charismatic, and emotionally intelligent dating advisor.\n"
            f"The conversation with {match_name} has stalled or gone quiet. Generate 3 mature, high-value, attractive follow-up messages to revive the chat.\n"
            f"Recent messages context:\n{last_msgs_text or 'No recent replies'}\n"
            f"Tone: {tone.upper()} ({tone_instruction})\n"
            f"Language: {language}\n"
            f"STRICT ADULT MATURITY STANDARDS (MEN & WOMEN LEVEL):\n"
            f"1. ADULT POISE: Sound confident, relaxed, and emotionally secure. Never sound needy, desperate, petty, or childish.\n"
            f"2. ZERO JUVENILE TROPES: Strictly NO jokes about kidnappers, being dead, sad violin music, astronaut on Mars, or whining about being ghosted.\n"
            f"3. ELEGANT RE-ENGAGEMENT: Use mature unbothered banter, genuine adult curiosity, witty executive charm, or intriguing conversational hooks that a self-respecting man or woman would send.\n"
            f"4. NATURAL DIALOGUE: In Hinglish or Hindi, write with sophistication and natural adult cadence.\n"
            f"5. Output strictly a valid JSON array of 3 strings: [\"line 1\", \"line 2\", \"line 3\"]. No markdown or intro text."
        )
        llm_resp = await call_gemini_llm(prompt)
        if llm_resp:
            try:
                clean_json = llm_resp
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0]
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0]
                parsed = json.loads(clean_json.strip())
                if isinstance(parsed, list) and len(parsed) >= 2:
                    return {
                        "suggestions": parsed[:4],
                        "tone": tone,
                        "language": language,
                        "engine": "gemini-ai"
                    }
            except Exception:
                pass

    pool = REVIVE_SUGGESTIONS.get(language, {}).get(tone, REVIVE_SUGGESTIONS["hinglish"]["mysterious"])
    sampled = random.sample(pool, min(len(pool), 4))
    return {
        "suggestions": sampled,
        "tone": tone,
        "language": language,
        "engine": "smart-context"
    }


def generate_profile_coach(
    user_profile: Dict[str, Any],
    language: str = "hinglish"
) -> Dict[str, Any]:
    """
    Analyzes user profile and returns a Strength Score (0-100) along with
    actionable tips to boost matches by 3x.
    """
    language = language.lower() if language in ["hinglish", "hindi", "english"] else "hinglish"

    photos = user_profile.get("photos", []) or []
    bio = user_profile.get("bio", "") or ""
    interests = user_profile.get("interests", []) or []
    prompts = user_profile.get("prompts", []) or []
    occupation = user_profile.get("occupation", "") or ""
    education = user_profile.get("education", "") or ""
    relationship_goals = user_profile.get("relationship_goals", "") or ""

    score = 0
    tips = []

    # 1. Photos Analysis (Max 40 pts)
    photo_count = len(photos)
    if photo_count >= 4:
        score += 40
    elif photo_count >= 2:
        score += 25
        if language == "hinglish":
            tips.append({
                "tag": "📸 Photos",
                "title": "2 Aur Photos Add Karo",
                "desc": "Kam se kam 4 photos rakhne se matches 2.5x badh jaate hain. Ek smiling outdoor photo add karo!"
            })
        elif language == "hindi":
            tips.append({
                "tag": "📸 फ़ोटो",
                "title": "2 और तस्वीरें जोड़ें",
                "desc": "कम से कम 4 फ़ोटो रखने से प्रोफ़ाइल को 2.5 गुना ज़्यादा लाइक्स मिलते हैं।"
            })
        else:
            tips.append({
                "tag": "📸 Photos",
                "title": "Add 2 More Photos",
                "desc": "Profiles with at least 4 photos get 2.5x more matches. Include an outdoor full-body shot!"
            })
    else:
        score += 10
        if language == "hinglish":
            tips.append({
                "tag": "🚨 Photos",
                "title": "Photos Upload Karo",
                "desc": "Ek photo se profiles par trust kam hota hai. Apni best 3-4 candid photos upload karo."
            })
        elif language == "hindi":
            tips.append({
                "tag": "🚨 फ़ोटो",
                "title": "और तस्वीरें अपलोड करें",
                "desc": "सिर्फ़ एक फ़ोटो से मैच मिलने की संभावना कम हो जाती है। अपनी 3-4 बेहतरीन फ़ोटो जोड़ें।"
            })
        else:
            tips.append({
                "tag": "🚨 Photos",
                "title": "Upload More Photos",
                "desc": "Single-photo profiles get 70% fewer matches. Add at least 3 high-quality portraits."
            })

    # 2. Bio Analysis (Max 25 pts)
    bio_words = len(bio.strip().split())
    if bio_words >= 15:
        score += 25
    elif bio_words >= 5:
        score += 15
        if language == "hinglish":
            tips.append({
                "tag": "✍️ Bio",
                "title": "Bio Me Thodi Detail Badhao",
                "desc": "Tumhe kya pasand hai aur weekend pe kya karte ho, yeh bio me add karo taaki log easily conversation start kar sakein."
            })
        elif language == "hindi":
            tips.append({
                "tag": "✍️ बायो",
                "title": "बायो को थोड़ा और आकर्षक बनाएं",
                "desc": "अपने शौक़ और वीकेंड के बारे में 2 लाइनें लिखें ताकि लोग आसानी से बात शुरू कर सकें।"
            })
        else:
            tips.append({
                "tag": "✍️ Bio",
                "title": "Add More Character to Bio",
                "desc": "Tell people what you nerd out on or what a typical Sunday looks like. Give them conversation bait!"
            })
    else:
        score += 5
        if language == "hinglish":
            tips.append({
                "tag": "✍️ Bio",
                "title": "Ek Engaging Bio Likho",
                "desc": "Khali bio se log swipe left kar dete hain. 2 witty lines likho apni personality ke baare me!"
            })
        elif language == "hindi":
            tips.append({
                "tag": "✍️ बायो",
                "title": "एक बढ़िया बायो लिखें",
                "desc": "खाली बायो से लोग आगे बढ़ जाते हैं। अपने व्यक्तित्व के बारे में 2 मज़ेदार लाइनें जोड़ें।"
            })
        else:
            tips.append({
                "tag": "✍️ Bio",
                "title": "Write an Engaging Bio",
                "desc": "A witty 2-line bio increases right-swipes by 60%. Share your vibe!"
            })

    # 3. Interests Analysis (Max 15 pts)
    if len(interests) >= 5:
        score += 15
    elif len(interests) >= 3:
        score += 10
    else:
        score += 5
        if language == "hinglish":
            tips.append({
                "tag": "🎯 Interests",
                "title": "5 Interests Select Karo",
                "desc": "Coffee, Travel, Music jaise 5 tags select karne se matching algorithm tumhare jaise vibes walo se connect karta hai."
            })
        elif language == "hindi":
            tips.append({
                "tag": "🎯 रुचियां",
                "title": "कम से कम 5 रुचियां चुनें",
                "desc": "कॉफ़ी, म्यूज़िक या ट्रैवल जैसे टैग जोड़ने से सही मैच ढूंढने में मदद मिलती है।"
            })
        else:
            tips.append({
                "tag": "🎯 Interests",
                "title": "Pick at least 5 Interests",
                "desc": "Selecting tags like Coffee, Travel, or Music helps our matchmaker find like-minded people."
            })

    # 4. Profile Prompts (Max 10 pts)
    if len(prompts) >= 2:
        score += 10
    elif len(prompts) == 1:
        score += 6
        if language == "hinglish":
            tips.append({
                "tag": "💡 Prompts",
                "title": "1 Aur Prompt Add Karo",
                "desc": "Prompts conversation ke sabse badhiya icebreakers hote hain. Ek funny prompt answer add karo!"
            })
        elif language == "hindi":
            tips.append({
                "tag": "💡 प्रॉमप्ट्स",
                "title": "1 और सवाल का जवाब जोड़ें",
                "desc": "प्रॉमप्ट्स बातचीत शुरू करने का सबसे आसान ज़रिया होते हैं।"
            })
        else:
            tips.append({
                "tag": "💡 Prompts",
                "title": "Add 1 More Prompt",
                "desc": "Prompts are the #1 conversation starter. Add one witty answer to spark chats!"
            })
    else:
        score += 2
        if language == "hinglish":
            tips.append({
                "tag": "💡 Prompts",
                "title": "Spark Prompts Add Karo",
                "desc": "Prompts add karne se samne wale ko pehla message bhejna 10x aasan lagta hai."
            })
        elif language == "hindi":
            tips.append({
                "tag": "💡 प्रॉमप्ट्स",
                "title": "प्रोफ़ाइल प्रॉमप्ट जोड़ें",
                "desc": "प्रॉमप्ट जोड़ने से सामने वाले के लिए बातचीत शुरू करना बहुत आसान हो जाता है।"
            })
        else:
            tips.append({
                "tag": "💡 Prompts",
                "title": "Add Profile Prompts",
                "desc": "Profiles with prompts receive 4x more first messages. Pick a prompt to show your sense of humor!"
            })

    # 5. Career & Relationship Goals (Max 10 pts)
    if occupation and relationship_goals:
        score += 10
    elif occupation or relationship_goals:
        score += 5
    else:
        if language == "hinglish":
            tips.append({
                "tag": "💼 Career & Goals",
                "title": "Job Aur Relationship Goal Set Karo",
                "desc": "Yeh batane se ki tum kya chahte ho (Long-term, Casual) genuine matches jaldi aate hain."
            })
        elif language == "hindi":
            tips.append({
                "tag": "💼 लक्ष्य",
                "title": "अपना काम और रिलेशनशिप गोल जोड़ें",
                "desc": "यह स्पष्ट करने से कि आप क्या ढूंढ रहे हैं, सही लोग आकर्षित होते हैं।"
            })
        else:
            tips.append({
                "tag": "💼 Goals",
                "title": "Set Relationship Intentions",
                "desc": "Being clear about what you're looking for attracts genuine and compatible people."
            })

    # Summary praise based on score
    if score >= 85:
        summary = "Tumhari profile super attractive hai! ✨ Minor tweaks se conversion aur badh sakti hai." if language == "hinglish" else ("आपकी प्रोफ़ाइल बहुत शानदार है! ✨" if language == "hindi" else "Your profile looks stellar! ✨ Ready to turn heads.")
    elif score >= 60:
        summary = "Solid profile! In 2-3 tips ko follow karke match rate 2x boost ho sakta hai 🚀" if language == "hinglish" else ("अच्छी प्रोफ़ाइल है! इन सुझावों से मैच रेट दोगुना हो सकता है 🚀" if language == "hindi" else "Solid profile! These quick tweaks can easily 2x your match rate 🚀")
    else:
        summary = "Bas thoda polish baaki hai! In tips se tumhari profile Spark par stand out karegi ⚡" if language == "hinglish" else ("बस थोड़ा सुधार बाक़ी है! इन सुझावों से आपकी प्रोफ़ाइल चमक उठेगी ⚡" if language == "hindi" else "A little polish will make a huge difference! Follow these tips to stand out ⚡")

    return {
        "score": min(score, 100),
        "summary": summary,
        "tips": tips[:4],
        "metrics": {
            "photosCount": photo_count,
            "bioLength": bio_words,
            "interestsCount": len(interests),
            "promptsCount": len(prompts)
        }
    }
