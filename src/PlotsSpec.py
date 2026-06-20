defaultSize = 2
default_stretch = 2
outliers_m = 5.

# Colours
loudness      = "#008b8b"
pitch         = "#e9aad8"
f1            = "#dc143c"
f2            = "#006400"
f3            = "#ffd700"

f1_pitch      = "#7588ff"
f2_pitch      = "#ff8c00"
f3_pitch      = "#9966cc"
weight        = "#c71585"
size          = "#32cd32"


white         = "#FFFFFFFF"


target_loudness = "#88888844"
target_pitch    = "#88888844"
target_f1       = "#88888844"
target_f2       = "#88888844"
target_f3       = "#88888844"
target_ratio_f3 = "#88888844"
target_ratio_f2 = "#88888844"
target_weight   = "#88888844"
target_white    = "#88888844"


spec = {
    'Loudness': {
        'title': 'Loudness',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': False,
        'y_min': 0,
        'y_max': 1,
        'curves': {
            'pitch': {
                'size': defaultSize,
                'colour': loudness,
                'analysisResult': 'loudness'
            }
        },
        'targets': {
            'Loudness': {'colour': target_loudness}
        },
        'linkX': None
    },

    'Pitch': {
        'title': 'Pitch (Hz)',
        'y_min': 0,
        'y_max': 350,
        'stretch': 1,
        'curves': {
            'pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'pitch',
            },
            'Pitch_BW': {
                'size': defaultSize,
                'colour': pitch,
                'analysisResult': 'Pitch_BW',
                'BW': True
            }
        },
        'targets': {
            'Pitch': {'colour': target_pitch}
        },
        'linkX': 'Loudness'
    },

    'Formants': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
        'hidden': True,
        'curves': {
            'F1': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F2'
            },
            'F3': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F3'
            },
            'F1_IBW': {
                'size': defaultSize,
                'colour': f1,
                'analysisResult': 'F1_IBW',
                'BW': True
            },
            'F2_IBW': {
                'size': defaultSize,
                'colour': f2,
                'analysisResult': 'F2_IBW',
                'BW': True
            },
            'F3_IBW': {
                'size': defaultSize,
                'colour': f3,
                'analysisResult': 'F3_IBW',
                'BW': True
            }
        },
        'targets': {
            'F1': {'colour': target_f1},
            'F2': {'colour': target_f2},
            'F3': {'colour': target_f3}
        },
        'linkX': 'Loudness'
    },

    'F3_Pitch': {
        'title': 'F3 / Pitch',
        'y_min': 1,
        'y_max': 50,
        'hidden': True,
        'curves': {
            'F3_Pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F3_Pitch'
            },
            "F3_Pitch_BW": {
                'size': defaultSize,
                'colour': f3_pitch,
                'analysisResult': 'F3_Pitch_BW',
                'BW': True
            },
        },
        'targets': {
            'F3_Pitch': {'colour': target_white}
        },
        'linkX': 'Loudness'
    },

    'F2_Pitch': {
        'title': 'F2 / Pitch',
        'y_min': 1,
        'y_max': 30,
        'hidden': True,
        'curves': {
            'F2_Pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F2_Pitch'
            },
            "F2_Pitch_BW": {
                'size': defaultSize,
                'colour': f2_pitch,
                'analysisResult': 'F2_Pitch_BW',
                'BW': True
            },
        },
        'targets': {
            'F2_Pitch': {'colour': target_white}
        },
        'linkX': 'Loudness'
    },

    'F1_Pitch': {
        'title': 'F1 / Pitch',
        'y_min': 1,
        'y_max': 15,
        'hidden': True,
        'curves': {
            'F1_Pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F1_Pitch'
            },
            "F1_Pitch_BW": {
                'size': defaultSize,
                'colour': f1_pitch,
                'analysisResult': 'F1_Pitch_BW',
                'BW': True
            },
        },
        'targets': {
            'F1_Pitch': {'colour': target_white}
        },
        'linkX': 'Loudness'
    },

    "Size": {
        'title': 'Size',
        'y_min': -15,
        'y_max': 25  ,
        'curves': {
            'size': {
                'size': defaultSize+1,
                'colour': size,
                'analysisResult': 'size'
            }
        },
        'targets': {
            'Size': {'colour': target_weight}
        },
        'linkX': 'Loudness',
    },

    "Weight": {
        'title': 'Weight',
        'y_min': 0,
        'y_max': 8.0e-7,
        'curves': {
            'weight': {
                'size': defaultSize+1,
                'colour': weight,
                'analysisResult': 'weight'
            }
        },
        'targets': {
            'Weight': {'colour': target_weight}
        },
        'linkX': 'Loudness',
    },

    "Fullness": {
        'title': 'Fullness',
        'y_min': -15,
        'y_max': 25,
        'curves': {
            'size_weight': {
                'size': defaultSize + 2,
                'colour': white,  # Fallback color
                'analysisResult': 'size', # Y-axis
                'colorSource': 'weight'   # Z-axis (Color)
            }
        },
        'targets': {
            'Size': {'colour': target_weight}
        },
        'linkX': 'Loudness',
    }
}