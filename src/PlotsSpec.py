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

h1_h2         = "#EF75F0"
h1_h3         = "#F07595"
h1_h4         = "#F0B175"
h1_a3         = "#C175F0"

jitter        = "#85E0BF"
shimmer       = "#85BCE0"

white         = "#88888888"

target_band = "#88888833"

spec = {
    'Pitch': {
        'title': 'Pitch (Hz)',
        'y_min': 0,
        'y_max': 350,
        'stretch': 1,
        'curves': {
            'Pitch': {
                'size': defaultSize,
                'colour': pitch,
                'analysisResult': 'pitch',
            },
        },
        'targets': {
            'Pitch': {'colour': target_band}
        }
    },

    "Size": {
        'title': 'Size',
        'y_min': 0,
        'y_max': 30,
        'curves': {
            'Size': {
                'size': defaultSize,
                'colour': size,
                'analysisResult': 'size'
            }
        },
        'targets': {
            'Size': {'colour': target_band}
        }
    },

    'Weight': {
        'title': 'Weight (softness)',
        'y_min': 0,
        'y_max': 2,
        'curves': {
            'Weight': {
                'size': defaultSize,
                'colour': weight,
                'analysisResult': 'weight_instantaneous',
            },
            # 'Weight 330 max max': {
            #     'size': defaultSize,
            #     'colour': 'blue',
            #     'analysisResult': 'weight_333ms_max',
            # },
        },
        'targets': {
            'Weight': {'colour': target_band}
        }
    },

    '5s average pitch': {
        'title': 'Pitch 5s average',
        'y_min': 0,
        'y_max': 300,
        'curves': {
            'Pitch': {
                'size': defaultSize,
                'colour': pitch,
                'analysisResult': 'pitch_5s_mean',
            },
        },
        'targets': {
            'Pitch': {'colour': target_band},
        }
    },

    '5s average size': {
        'title': 'Size 5s average',
        'y_min': 0,
        'y_max': 30,
        'curves': {
            'Size': {
                'size': defaultSize,
                'colour': size,
                'analysisResult': 'size_5s_mean',
            },
        },
        'targets': {
            'Size': {'colour': target_band},
        }
    },

    '5s average weight': {
        'title': 'Weight 5s average',
        'y_min': 0,
        'y_max': 40,
        'curves': {
            'Weight 330 max max': {
                'size': defaultSize,
                'colour': weight,
                'analysisResult': 'weight_333ms_max',
            },
        },
        'targets': {
            'Weight': {'colour': target_band},
        }
    },

    'Loudness': {
        'title': 'Loudness',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': False,
        'y_min': 0,
        'y_max': 10,
        'curves': {
            'Loudness': {
                'size': defaultSize,
                'colour': loudness,
                'analysisResult': 'loudness'
            }
        },
        'targets': {
            'Loudness': {'colour': target_band}
        }
    },

    "Spectral slopes": {
        'title': 'Spectral slopes',
        'y_min': -1e-6,
        'y_max': 1e-6,
        'curves': {
            'Spectral slopes': {
                'size': defaultSize,
                'colour': 'red',
                'analysisResult': 'slopes'
            }
        },
        'targets': {
            'slopes': {'colour': target_band}
        }
    },

    'Formants': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
        'curves': {
            'F1': {
                'size': defaultSize,
                'colour': f1,
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'size': defaultSize,
                'colour': f2,
                'analysisResult': 'F2'
            },
            'F3': {
                'size': defaultSize,
                'colour': f3,
                'analysisResult': 'F3'
            },
        },
        'targets': {
            'F1': {'colour': target_band},
            'F2': {'colour': target_band},
            'F3': {'colour': target_band}
        }
    },

    'F1': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
        'curves': {
            'F1': {
                'size': defaultSize,
                'colour': f1,
                'analysisResult': 'F1'
            },
        },
        'targets': {
            'F1': {'colour': target_band},
        }
    },

    'F2': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
        'curves': {
            'F2': {
                'symbol': 'o',
                'size': defaultSize,
                'colour': f2,
                'analysisResult': 'F2'
            },
        },
        'targets': {
            'F2': {'colour': target_band},
        }
    },

    'F3': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
        'curves': {
            'F3': {
                'size': defaultSize,
                'colour': f3,
                'analysisResult': 'F3'
            },
        },
        'targets': {
            'F3': {'colour': target_band}
        }
    },

    'F3/Pitch': {
        'title': 'F3 / Pitch',
        'y_min': 1,
        'y_max': 50,
        'curves': {
            'F3/Pitch': {
                'size': defaultSize,
                'colour': f3_pitch,
                'analysisResult': 'F3_Pitch'
            },
        },
        'targets': {
            'F3_Pitch': {'colour': target_band}
        }
    },

    'F2/Pitch': {
        'title': 'F2 / Pitch',
        'y_min': 1,
        'y_max': 30,
        'curves': {
            'F2/Pitch': {
                'size': defaultSize,
                'colour': f2_pitch,
                'analysisResult': 'F2_Pitch'
            },
        },
        'targets': {
            'F2_Pitch': {'colour': target_band}
        }
    },

    'F1/Pitch': {
        'title': 'F1 / Pitch',
        'y_min': 1,
        'y_max': 15,
        'curves': {
            'F1/Pitch': {
                'size': defaultSize,
                'colour': f1_pitch,
                'analysisResult': 'F1_Pitch'
            },
        },
        'targets': {
            'F1_Pitch': {'colour': target_band}
        }
    },

    "Fullness": {
        'title': 'Fullness',
        'y_min': -15,
        'y_max': 25,
        'curves': {
            'Fullness': {
                'size': defaultSize,
                'colour': white,  # Fallback color
                'analysisResult': 'size', # Y-axis
                'colorSource': 'weight_instantaneous'   # Z-axis (Color)
            }
        },
        'targets': {
            'Size': {'colour': target_band}
        }
    },

    'Spectrogram': {
        'title': 'Time - Frequency & Magnitude',
        'y_min': 0,
        'y_max': 8000,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'curves': {
            'Spectrogram': {
                'analysisResult': 'spectrogram',
                'is_spectrogram': True,  # The flag our PlotController looks for
                'colour': 'viridis',
            },
        }
    },

    'Frequency Analysis': {
        'title': 'Frequency - Magnitude',
        'mouse_enabled_x': False,
        'mouse_enabled_y': False,
        'y_min': -90,
        'y_max': 0,
        'x_min': 10,  # Start at 10Hz to prevent log(0) crashes
        'x_max': 10000,  # Max frequency 10kHz
        'log_x': True,
        'x_ticks': [10, 110, 220, 1000, 5000, 10000],  # X-axis labels
        'curves': {
            'Spectrum': {
                'analysisResult': 'spectrogram',
                'is_frequency_analysis': True,
                'colour': '#9370DB',
                'fill_colour': (147, 112, 219, 150)
            },
        }
    },


    "H1_H2": {
        'title': 'H1_H2',
        'y_min': -20,
        'y_max': 50,
        'curves': {
            'H1_H2': {
                'size': defaultSize,
                'colour': h1_h2,
                'analysisResult': 'H1_H2'
            }
        },
        'targets': {
            'H1_H2': {'colour': target_band}
        }
    },

    "H1_H3": {
        'title': 'H1_H3',
        'y_min': -20,
        'y_max': 50,
        'curves': {
            'H1_H3': {
                'size': defaultSize,
                'colour': h1_h3,
                'analysisResult': 'H1_H3'
            }
        },
        'targets': {
            'H1_H3': {'colour': target_band}
        }
    },

    "H1_H4": {
        'title': 'H1_H4',
        'y_min': -20,
        'y_max': 50,
        'curves': {
            'H1_H4': {
                'size': defaultSize,
                'colour': h1_h4,
                'analysisResult': 'H1_H4'
            }
        },
        'targets': {
            'H1_H4': {'colour': target_band}
        }
    },

    "H1_A3": {
        'title': 'H1_A3',
        'y_min': -20,
        'y_max': 50,
        'curves': {
            'H1_A3': {
                'size': defaultSize,
                'colour': h1_a3,
                'analysisResult': 'H1_A3'
            }
        },
        'targets': {
            'H1_A3': {'colour': target_band}
        }
    },

    "Jitter": {
        'title': 'Jitter',
        'y_min': 0,
        'y_max': 0.2,
        'curves': {
            'Jitter': {
                'size': defaultSize,
                'colour': jitter,
                'analysisResult': 'jitter'
            }
        },
        # 'targets': {
        #     'H1_A3': {'colour': target_band}
        # }
    },

    "Shimmer": {
        'title': 'Shimmer',
        'y_min': 0,
        'y_max': 7,
        'curves': {
            'Shimmer': {
                'size': defaultSize,
                'colour': shimmer,
                'analysisResult': 'shimmer'
            }
        },
        # 'targets': {
        #     'H1_A3': {'colour': target_band}
        # }
    },
}