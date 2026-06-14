defaultSize = 1
default_stretch = 2
outliers_m = 5.

# Colours
loudness      = "#00ffffFF"
pitch         = "#ff00ffAA"
ratio_f2_f1   = "#37ff144b"
ratio_f3_f1   = "#ffd9007c"
f1            = "#00bfff6e"
f2            = "#ff7f5073"
f3            = "#ba55d377"
weight        = "#fc4b60FF"
white         = "#FFFFFFFF"

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
        'linkX': None
    },

    'Pitch': {
        'title': 'Pitch (Hz)',
        'y_min': 0,
        'y_max': 350,
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
        'linkX': 'Loudness'
    },

    'Formants': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
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
        'linkX': 'Loudness'
    },

    'F3_Pitch': {
        'title': 'F3 / Pitch',
        # 'y_min': 1,
        # 'y_max': 9,
        'curves': {
            'F3_Pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F3_Pitch'
            },
            "F3_Pitch_BW": {
                'size': defaultSize,
                'colour': f3,
                'analysisResult': 'F3_Pitch_BW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },

    'F2_Pitch': {
        'title': 'F2 / Pitch',
        # 'y_min': 1,
        # 'y_max': 9,
        'curves': {
            'F2_Pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F2_Pitch'
            },
            "F2_Pitch_BW": {
                'size': defaultSize,
                'colour': f2,
                'analysisResult': 'F2_Pitch_BW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },

    'F1_Pitch': {
        'title': 'F1 / Pitch',
        # 'y_min': 1,
        # 'y_max': 9,
        'curves': {
            'F1_Pitch': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F1_Pitch'
            },
            "F1_Pitch_BW": {
                'size': defaultSize,
                'colour': f1,
                'analysisResult': 'F1_Pitch_BW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },

    'F3_F1': {
        'title': 'Formant ratio F3/F1',
        'y_min': 1,
        'y_max': 9,
        'curves': {
            'F3_F1': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F3_F1'
            },
            "F3_F1_IBW": {
                'size': defaultSize,
                'colour': ratio_f3_f1,
                'analysisResult': 'F3_F1_IBW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },

    'F2_F1': {
        'title': 'Formant ratio F2/F1',
        'y_min': 1,
        'y_max': 5,
        'curves': {
            'F2_F1': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F2_F1'
            },
            "F2_F1_IBW": {
                'size': defaultSize,
                'colour': ratio_f2_f1,
                'analysisResult': 'F2_F1_IBW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },

    "Weight": {
        'title': 'Weight',
        'y_min': 0,
        'y_max': 4.0e-7,
        'curves': {
            'slopes': {
                'size': defaultSize+1,
                'colour': weight,
                'analysisResult': 'slopes'
            }
        },
        'linkX': 'Loudness',
    }
}